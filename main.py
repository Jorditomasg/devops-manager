#!/usr/bin/env python3
"""
DevOps Manager — Entry Point
A desktop tool to manage all your development repositories.
"""
import os
import sys

# Ensure the project root is in the path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def main():
    # Set Windows AppUserModelID early so custom icon is used in taskbar
    if sys.platform == 'win32':
        import ctypes
        try:
            myappid = 'devops_manager.app.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    # Default workspace = parent directory of this tool
    workspace_dir = os.path.dirname(project_root)

    # Allow overriding via CLI argument
    if len(sys.argv) > 1:
        workspace_dir = sys.argv[1]
        if not os.path.isdir(workspace_dir):
            print(f"Error: El directorio '{workspace_dir}' no existe.")
            sys.exit(1)

    # Import and launch
    from gui.app import DevOpsManagerApp
    app = DevOpsManagerApp(workspace_dir=workspace_dir)
    app.mainloop()


if __name__ == '__main__':
    main()
