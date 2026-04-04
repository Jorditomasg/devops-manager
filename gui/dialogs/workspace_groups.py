"""workspace_groups.py — Dialog for managing named workspace groups."""
import copy
import os
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.config_manager import get_workspace_groups, set_workspace_groups, get_active_group, set_active_group
from core.i18n import t
from gui.dialogs._base import BaseDialog
from gui import theme


class WorkspaceGroupsDialog(BaseDialog):
    """Dialog for managing workspace groups (named sets of directories)."""

    def __init__(self, parent, on_groups_changed=None):
        self._on_groups_changed = on_groups_changed
        super().__init__(parent, title=t("dialog.workspace_groups.title"), width=620, height=480)
        self._build_form_content()

    def _build_form_content(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=12)
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=2)
        container.grid_rowconfigure(1, weight=1)

        # ── Left: group list ─────────────────────────────────────────
        left = ctk.CTkFrame(container, fg_color="transparent")
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text=t("dialog.workspace_groups.groups_label"),
                     font=theme.font("sm", bold=True)).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._groups_listbox = tk.Listbox(
            left, selectmode=tk.SINGLE, activestyle="none",
            bg=theme.C.card, fg=theme.C.text_primary,
            selectbackground=theme.C.text_accent, selectforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=1,
            highlightcolor=theme.C.card_border, font=theme.font("base")
        )
        self._groups_listbox.grid(row=1, column=0, sticky="nsew")
        self._groups_listbox.bind("<<ListboxSelect>>", self._on_group_select)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        ctk.CTkButton(btn_row, text=t("btn.add_group"), width=60,
                      **theme.btn_style("blue", height="sm"),
                      command=self._add_group).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text=t("btn.delete_group"), width=60,
                      **theme.btn_style("danger", height="sm"),
                      command=self._delete_group).pack(side="left")

        # ── Right: group editor ──────────────────────────────────────
        right = ctk.CTkFrame(container, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="nsew")
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text=t("dialog.workspace_groups.name_label"),
                     font=theme.font("sm", bold=True)).grid(row=0, column=0, sticky="w", pady=(0, 2))

        name_row = ctk.CTkFrame(right, fg_color="transparent")
        name_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        name_row.grid_columnconfigure(0, weight=1)

        self._name_entry = ctk.CTkEntry(name_row, placeholder_text=t("dialog.workspace_groups.name_placeholder"))
        self._name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(name_row, text=t("btn.rename"), width=70,
                      **theme.btn_style("neutral", height="sm"),
                      command=self._rename_group).grid(row=0, column=1)

        ctk.CTkLabel(right, text=t("dialog.workspace_groups.paths_label"),
                     font=theme.font("sm", bold=True)).grid(row=2, column=0, sticky="w", pady=(0, 2))

        paths_frame = ctk.CTkFrame(right)
        paths_frame.grid(row=3, column=0, sticky="nsew")
        paths_frame.grid_rowconfigure(0, weight=1)
        paths_frame.grid_columnconfigure(0, weight=1)

        self._paths_listbox = tk.Listbox(
            paths_frame, selectmode=tk.SINGLE, activestyle="none",
            bg=theme.C.card, fg=theme.C.text_primary,
            selectbackground=theme.C.text_accent, selectforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=1,
            highlightcolor=theme.C.card_border, font=theme.font("sm")
        )
        self._paths_listbox.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        paths_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        paths_btn_row.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        ctk.CTkButton(paths_btn_row, text=t("btn.add_path"), width=80,
                      **theme.btn_style("blue", height="sm"),
                      command=self._add_path).pack(side="left", padx=(0, 4))
        ctk.CTkButton(paths_btn_row, text=t("btn.remove_path"), width=80,
                      **theme.btn_style("danger", height="sm"),
                      command=self._remove_path).pack(side="left")

        # ── Save button ──────────────────────────────────────────────
        ctk.CTkButton(container, text=t("btn.save"),
                      **theme.btn_style("success"),
                      command=self._save).grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

        # Load data
        self._groups = get_workspace_groups()
        self._initial_groups = copy.deepcopy(self._groups)
        self._active_group = get_active_group()
        self._selected_idx = None
        self._refresh_groups_list()
        # Select active group by default
        active = self._active_group
        names = [g["name"] for g in self._groups]
        if active in names:
            idx = names.index(active)
            self._groups_listbox.selection_set(idx)
            self._groups_listbox.activate(idx)
            self._on_group_select(None)
        elif names:
            self._groups_listbox.selection_set(0)
            self._groups_listbox.activate(0)
            self._on_group_select(None)

    def _refresh_groups_list(self):
        self._groups_listbox.delete(0, tk.END)
        for g in self._groups:
            self._groups_listbox.insert(tk.END, g["name"])

    def _on_group_select(self, _event):
        sel = self._groups_listbox.curselection()
        if not sel:
            return
        self._selected_idx = sel[0]
        group = self._groups[self._selected_idx]
        self._name_entry.delete(0, tk.END)
        self._name_entry.insert(0, group["name"])
        self._refresh_paths_list(group["paths"])

    def _refresh_paths_list(self, paths):
        self._paths_listbox.delete(0, tk.END)
        for p in paths:
            self._paths_listbox.insert(tk.END, p)

    def _add_group(self):
        name = t("dialog.workspace_groups.new_group_name")
        existing = {g["name"] for g in self._groups}
        i = 1
        candidate = name
        while candidate in existing:
            candidate = f"{name} {i}"
            i += 1
        self._groups.append({"name": candidate, "paths": []})
        self._refresh_groups_list()
        idx = len(self._groups) - 1
        self._groups_listbox.selection_clear(0, tk.END)
        self._groups_listbox.selection_set(idx)
        self._groups_listbox.activate(idx)
        self._on_group_select(None)

    def _delete_group(self):
        if self._selected_idx is None:
            return
        if len(self._groups) <= 1:
            return  # must keep at least one group
        deleted_idx = self._selected_idx
        del self._groups[deleted_idx]
        self._selected_idx = None
        self._refresh_groups_list()
        if self._groups:
            new_idx = min(deleted_idx, len(self._groups) - 1)
            self._groups_listbox.selection_clear(0, tk.END)
            self._groups_listbox.selection_set(new_idx)
            self._groups_listbox.activate(new_idx)
            self._on_group_select(None)

    def _rename_group(self):
        if self._selected_idx is None:
            return
        new_name = self._name_entry.get().strip()
        if not new_name:
            return
        for i, g in enumerate(self._groups):
            if i != self._selected_idx and g["name"] == new_name:
                return
        self._groups[self._selected_idx]["name"] = new_name
        self._refresh_groups_list()
        self._groups_listbox.selection_set(self._selected_idx)

    def _add_path(self):
        if self._selected_idx is None:
            return
        path = filedialog.askdirectory(title=t("dialog.workspace_groups.browse_title"))
        if path and path not in self._groups[self._selected_idx]["paths"]:
            self._groups[self._selected_idx]["paths"].append(path)
            self._refresh_paths_list(self._groups[self._selected_idx]["paths"])
            # Auto-save and trigger rescan immediately
            set_workspace_groups(self._groups)
            if self._on_groups_changed:
                self._on_groups_changed(self._groups)

    def _remove_path(self):
        if self._selected_idx is None:
            return
        sel = self._paths_listbox.curselection()
        if not sel:
            return
        paths = self._groups[self._selected_idx]["paths"]
        del paths[sel[0]]
        self._refresh_paths_list(paths)

    def _save(self):
        empty = [g["name"] for g in self._groups if not g.get("paths")]
        if empty:
            messagebox.showerror(
                t("misc.warning_title"),
                t("dialog.workspace_groups.error_empty_paths", names=", ".join(empty))
            )
            return
        set_workspace_groups(self._groups)
        names = [g["name"] for g in self._groups]
        if self._active_group not in names and names:
            set_active_group(names[0])
        if self._on_groups_changed and self._groups != self._initial_groups:
            self._on_groups_changed(self._groups)
        self.destroy()
