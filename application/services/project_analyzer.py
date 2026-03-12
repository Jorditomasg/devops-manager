import os
import re
from typing import List, Optional, Dict, Any
from domain.models.repo_info import RepoInfo
from infrastructure.config.yaml_parser import YamlParser

class ProjectAnalyzerService:
    """
    Scans a workspace and uses Config-Driven Definitions to identify repositories.
    """
    
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.repo_types = self._load_repo_types()
        
    def _load_repo_types(self) -> List[Dict[str, Any]]:
        """Loads all YAML definitions from the config/repo_types folder."""
        repo_types = []
        repo_types_dir = os.path.join(self.config_dir, "repo_types")
        if not os.path.isdir(repo_types_dir):
            return repo_types

        for file in os.listdir(repo_types_dir):
            if file.endswith(('.yml', '.yaml')):
                config = YamlParser.load(os.path.join(repo_types_dir, file))
                if config and 'type' in config:
                    repo_types.append(config)

        # Sort by priority descending: higher priority = evaluated first.
        # docker-infra should always be last (lowest priority / fallback).
        repo_types.sort(key=lambda t: t.get('priority', 0), reverse=True)
        return repo_types

    def detect_repos(self, workspace_dir: str) -> List[RepoInfo]:
        """Scan workspace_dir for valid repositories matching known definitions."""
        repos = []
        if not os.path.isdir(workspace_dir):
            return repos

        # Determine the tool's own directory to skip it
        tool_dir = os.path.normpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        for entry in sorted(os.listdir(workspace_dir)):
            full_path = os.path.join(workspace_dir, entry)
            if not os.path.isdir(full_path):
                continue
            if entry.startswith('.') or entry == 'node_modules':
                continue
            # Skip the devops-manager tool itself
            if os.path.normpath(full_path) == tool_dir:
                continue

            repo = self._classify_repo(entry, full_path)
            if repo:
                repos.append(repo)

        return repos

    def _classify_repo(self, name: str, path: str) -> Optional[RepoInfo]:
        """Classifies a directory against all loaded repo_types."""
        # Check all files once to avoid multiple os.walk or os.path.isfile calls
        files_in_root = set()
        for item in os.listdir(path):
            if os.path.isfile(os.path.join(path, item)):
                files_in_root.add(item)
                
        # To avoid conflicts, we prioritize types based on their complexity. 
        # But for now, returning the first one that perfectly matches all rules.
        
        for r_type in self.repo_types:
            if self._matches_definition(r_type, files_in_root, path):
                return self._build_repo_info(name, path, r_type)
                
        return None

    def _matches_definition(self, r_type: Dict[str, Any], files_in_root: set, path: str) -> bool:
        """Checks if a path matches the given repository type definition rules."""
        import fnmatch
        detection = r_type.get('detection', {})
        repo_type_name = r_type.get('type', '')

        # Docker-infra can exist without .git; all others must have it
        has_git = os.path.isdir(os.path.join(path, '.git'))
        if repo_type_name != 'docker-infra' and not has_git:
            return False

        # 1. Required Files
        required_files = detection.get('required_files', [])
        for req in required_files:
            if req not in files_in_root:
                return False

        # 2. Excluded files
        exclude_files = detection.get('exclude_files', [])
        for excl in exclude_files:
            if excl in files_in_root:
                return False

        # 3. Heuristics
        heuristics = r_type.get('heuristics', {})

        must_have_dirs = heuristics.get('must_have_directories', [])
        for d in must_have_dirs:
            if not os.path.isdir(os.path.join(path, d)):
                return False

        must_not_have_dirs = heuristics.get('must_not_have_directories', [])
        for d in must_not_have_dirs:
            if os.path.isdir(os.path.join(path, d)):
                return False

        # 4. must_match_patterns — at least ONE file in root matches ANY pattern
        must_match = heuristics.get('must_match_patterns', [])
        if must_match:
            matched = any(
                any(fnmatch.fnmatch(f, pattern) for pattern in must_match)
                for f in files_in_root
            )
            if not matched:
                # Also search recursively in src/main/resources for Spring Boot patterns
                if repo_type_name == 'spring-boot':
                    resources = os.path.join(path, 'src', 'main', 'resources')
                    if os.path.isdir(resources):
                        matched = any(
                            any(fnmatch.fnmatch(f, p) for p in must_match)
                            for f in os.listdir(resources)
                            if os.path.isfile(os.path.join(resources, f))
                        )
                if not matched:
                    return False

        # 5. For docker-infra: must have at least one docker-compose file
        if repo_type_name == 'docker-infra':
            dc_patterns = heuristics.get('must_match_patterns', ['docker-compose*.yml', 'docker-compose*.yaml'])
            has_dc = any(
                any(fnmatch.fnmatch(f, p) for p in dc_patterns)
                for f in files_in_root
            )
            if not has_dc:
                return False

        return True

    def _build_repo_info(self, name: str, path: str, r_type: Dict[str, Any]) -> RepoInfo:
        """Build a RepoInfo instance from the matched configuration."""
        
        repo = RepoInfo(name=name, path=path, repo_type=r_type.get('type'))
        
        commands = r_type.get('commands', {})
        repo.run_command = self._resolve_run_command(path, commands)
        repo.run_profile_flag = commands.get('profile_flag')
        repo.run_install_cmd = commands.get('install_cmd')
        repo.run_reinstall_cmd = commands.get('reinstall_cmd')
        
        # Inject UI config and features
        if 'ui' in r_type:
            repo.ui_config = r_type['ui']
            
        if 'features' in r_type:
            repo.features = r_type['features']
        
        env_files_conf = r_type.get('env_files', {})
        env_files, profiles = self._resolve_env_files(path, repo.repo_type, env_files_conf)
        
        repo.environment_files = env_files
        repo.profiles = profiles
        
        return repo

    def _resolve_run_command(self, path: str, commands: Dict[str, Any]) -> Optional[str]:
        cmd = commands.get('start_cmd')
        
        if os.name == 'nt' and 'windows_start_cmd' in commands:
            cmd = commands.get('windows_start_cmd')
        elif os.name != 'nt' and 'unix_start_cmd' in commands:
            cmd = commands.get('unix_start_cmd')
            
        if cmd and '{main_app}' in cmd:
            apps_dir = os.path.join(path, 'apps')
            if os.path.isdir(apps_dir):
                apps = [d for d in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, d)) and not d.startswith('.')]
                main_app = apps[0] if apps else 'app'
                cmd = cmd.replace('{main_app}', main_app)
                
        return cmd

    def _resolve_env_files(self, path: str, repo_type: str, env_files_conf: Dict[str, Any]) -> tuple[List[str], List[str]]:
        patterns = env_files_conf.get('patterns', [])
        exclude_dirs = env_files_conf.get('exclude_dirs', ['.git', 'node_modules'])
        
        env_files_found = []
        profiles_found = set()
        
        if not patterns:
            return env_files_found, list(profiles_found)
            
        import fnmatch
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                for pattern in patterns:
                    if fnmatch.fnmatch(f, pattern):
                        env_files_found.append(os.path.join(root, f))
                        self._extract_profile_from_filename(f, pattern, profiles_found)

        if repo_type == 'spring-boot' and any(f.endswith(('application.yml', 'application.yaml', 'application.properties')) for f in env_files_found):
            profiles_found.add('default')
            
        return env_files_found, sorted(profiles_found)

    def _extract_profile_from_filename(self, filename: str, pattern: str, profiles_found: set):
        if 'environment' in pattern:
            match = re.match(r'environment\.?(.*)\.ts', filename)
            if match:
                prof = match.group(1) or 'default'
                profiles_found.add(prof)
        elif 'application' in pattern:
            match = re.match(r'application-(.+)\.(yml|yaml|properties)$', filename)
            if match:
                profiles_found.add(match.group(1))
