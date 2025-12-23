"""Projects + Knowledge Base surface.

Spec:
- Projects is its own surface (not Chat).
- Projects are folders under projects/<project-id>/kb/.
- Selecting a project opens its KB as a navigable tree of markdown pages.
- Selecting a page opens it in a dedicated document editor pane.
- Nothing is written without an explicit, user-confirmed diff preview.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db import Database
from ..projects_fs import (
    ensure_project_skeleton,
    extract_repo_path,
    get_project_paths,
    is_valid_project_id,
    list_project_ids,
    projects_root,
    read_text,
    workspace_root,
)

logger = logging.getLogger(__name__)


_PATH_ROLE = Qt.ItemDataRole.UserRole
_KIND_ROLE = Qt.ItemDataRole.UserRole + 1


def _rel_to_workspace(path: Path) -> str:
    return str(path.relative_to(workspace_root()))


def _safe_name(name: str) -> str:
    # Minimal guardrail: avoid path traversal and empty names.
    if not name or name.strip() == "":
        raise ValueError("Name is required")
    name = name.strip()
    if name.startswith("/") or ".." in name.split("/") or "\\" in name:
        raise ValueError("Invalid name")
    return name


@dataclass(frozen=True)
class _OpenDoc:
    abs_path: Path
    rel_path: str
    original_text: str


class _DiffConfirmDialog(QDialog):
    def __init__(self, *, parent: QWidget, title: str, diff_text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        root = QVBoxLayout(self)

        label = QLabel("Preview (unified diff)")
        label.setStyleSheet("font-weight: 600;")
        root.addWidget(label)

        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlainText(diff_text or "(no changes)")
        box.setMinimumSize(900, 520)
        root.addWidget(box, stretch=1)

        buttons = QHBoxLayout()
        root.addLayout(buttons)

        buttons.addStretch(1)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.accept)
        buttons.addWidget(apply_btn)


class ProjectsWidget(QWidget):
    """Filesystem-backed Projects + KB browser/editor."""

    def __init__(self, *, db: Database) -> None:
        super().__init__()
        self._db = db

        self._selected_project_id: str | None = None
        self._open_doc: _OpenDoc | None = None

        outer = QVBoxLayout(self)

        header_row = QHBoxLayout()
        outer.addLayout(header_row)

        title = QLabel("Projects")
        title.setProperty("reosTitle", True)
        header_row.addWidget(title)

        header_row.addStretch(1)

        self._new_project_id = QLineEdit()
        self._new_project_id.setPlaceholderText("new project id (e.g. reos)")
        self._new_project_id.setMaximumWidth(260)
        header_row.addWidget(self._new_project_id)

        self._new_btn = QPushButton("Create")
        self._new_btn.clicked.connect(self._on_create_project)
        header_row.addWidget(self._new_btn)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, stretch=1)

        # Left: unified project + KB tree (like a file explorer)
        left = QWidget()
        left_layout = QVBoxLayout(left)

        tree_label = QLabel("Projects + Knowledge Base")
        tree_label.setProperty("reosTitle", True)
        left_layout.addWidget(tree_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        left_layout.addWidget(self.tree, stretch=1)

        add_row = QHBoxLayout()
        left_layout.addLayout(add_row)

        self._new_item_name = QLineEdit()
        self._new_item_name.setPlaceholderText("new item name (e.g. notes.md or folder)")
        add_row.addWidget(self._new_item_name, stretch=1)

        self._new_file_btn = QPushButton("New File")
        self._new_file_btn.clicked.connect(self._on_new_file)
        add_row.addWidget(self._new_file_btn)

        self._new_folder_btn = QPushButton("New Folder")
        self._new_folder_btn.clicked.connect(self._on_new_folder)
        add_row.addWidget(self._new_folder_btn)

        split.addWidget(left)

        # Right: document editor
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.doc_path_label = QLabel("(no document selected)")
        self.doc_path_label.setProperty("reosMuted", True)
        right_layout.addWidget(self.doc_path_label)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Select a KB page to view/edit…")
        right_layout.addWidget(self.editor, stretch=1)

        actions = QHBoxLayout()
        right_layout.addLayout(actions)

        self.link_repo_btn = QPushButton("Link repoPath…")
        self.link_repo_btn.clicked.connect(self._on_link_repo)
        actions.addWidget(self.link_repo_btn)

        actions.addStretch(1)

        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self._reload_open_document)
        actions.addWidget(self.reload_btn)

        self.save_btn = QPushButton("Save (preview diff)")
        self.save_btn.clicked.connect(self._on_save_document)
        actions.addWidget(self.save_btn)

        split.addWidget(right)

        # Default sizes: tree (35%), editor (65%)
        split.setSizes([420, 780])

        self.refresh()

    def refresh(self) -> None:
        projects_root().mkdir(parents=True, exist_ok=True)

        selected_project = self._selected_project_id
        selected_rel = self._open_doc.rel_path if self._open_doc else None
        expanded = self._snapshot_expanded_nodes()

        self._populate_tree_all_projects()
        self._restore_expanded_nodes(expanded)

        # Best-effort restore selection.
        if isinstance(selected_rel, str):
            self._select_by_rel_path(selected_rel)
        elif isinstance(selected_project, str):
            self._select_project(selected_project)

    def _on_create_project(self) -> None:
        project_id = self._new_project_id.text().strip().lower()
        if not project_id:
            QMessageBox.warning(self, "Missing project id", "Enter a project id.")
            return
        if not is_valid_project_id(project_id):
            QMessageBox.warning(
                self,
                "Invalid project id",
                "Use 2-64 chars: a-z, 0-9, '-' or '_', starting with a letter/number.",
            )
            return

        try:
            ensure_project_skeleton(project_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create project")
            QMessageBox.critical(self, "Create failed", str(exc))
            return

        self._new_project_id.clear()
        self.refresh()

        self._select_project(project_id)

    def _populate_tree_all_projects(self) -> None:
        self.tree.clear()

        root_dir = projects_root()
        for project_id in list_project_ids():
            project_item = QTreeWidgetItem([project_id])
            project_item.setData(0, _KIND_ROLE, "project")
            project_item.setData(0, _PATH_ROLE, project_id)
            self.tree.addTopLevelItem(project_item)

            paths = get_project_paths(project_id)
            kb_dir = paths.kb_dir
            kb_item = QTreeWidgetItem(["kb"])
            kb_item.setData(0, _KIND_ROLE, "dir")
            kb_item.setData(0, _PATH_ROLE, _rel_to_workspace(kb_dir))
            project_item.addChild(kb_item)

            def add_file(parent: QTreeWidgetItem, abs_path: Path) -> None:
                if not abs_path.exists() or not abs_path.is_file():
                    return
                it = QTreeWidgetItem([abs_path.name])
                it.setData(0, _KIND_ROLE, "file")
                it.setData(0, _PATH_ROLE, _rel_to_workspace(abs_path))
                parent.addChild(it)

            def add_dir(parent: QTreeWidgetItem, abs_path: Path, label: str | None = None) -> QTreeWidgetItem:
                it = QTreeWidgetItem([label or abs_path.name])
                it.setData(0, _KIND_ROLE, "dir")
                it.setData(0, _PATH_ROLE, _rel_to_workspace(abs_path))
                parent.addChild(it)
                return it

            add_file(kb_item, paths.charter_md)
            add_file(kb_item, paths.roadmap_md)
            add_file(kb_item, paths.settings_md)

            pages_root = paths.pages_dir
            tables_root = paths.tables_dir
            if pages_root.exists():
                pages_item = add_dir(kb_item, pages_root, "pages")
                self._populate_dir_tree(pages_item, pages_root, allowed_exts={".md", ".markdown"})
            if tables_root.exists():
                tables_item = add_dir(kb_item, tables_root, "tables")
                self._populate_dir_tree(tables_item, tables_root, allowed_exts={".md", ".csv"})

            project_item.setExpanded(True)
            kb_item.setExpanded(True)

        root_dir.mkdir(parents=True, exist_ok=True)
        self.tree.expandToDepth(2)

    def _populate_dir_tree(
        self,
        parent_item: QTreeWidgetItem,
        dir_path: Path,
        *,
        allowed_exts: set[str],
    ) -> None:
        """Populate a folder subtree under parent_item."""

        if not dir_path.exists() or not dir_path.is_dir():
            return

        # Build directory nodes first (stable ordering), then files.
        dirs = sorted([p for p in dir_path.iterdir() if p.is_dir()])
        files = sorted([p for p in dir_path.iterdir() if p.is_file()])

        for d in dirs:
            d_item = QTreeWidgetItem([d.name])
            d_item.setData(0, _KIND_ROLE, "dir")
            d_item.setData(0, _PATH_ROLE, _rel_to_workspace(d))
            parent_item.addChild(d_item)
            self._populate_dir_tree(d_item, d, allowed_exts=allowed_exts)

        for f in files:
            if f.suffix.lower() not in allowed_exts:
                continue
            f_item = QTreeWidgetItem([f.name])
            f_item.setData(0, _KIND_ROLE, "file")
            f_item.setData(0, _PATH_ROLE, _rel_to_workspace(f))
            parent_item.addChild(f_item)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        kind = item.data(0, _KIND_ROLE)
        token = item.data(0, _PATH_ROLE)

        if kind == "project" and isinstance(token, str) and token:
            self._selected_project_id = token
            self._db.set_active_project_id(project_id=token)
            return

        if kind != "file" or not isinstance(token, str) or not token:
            return

        abs_path = (workspace_root() / token).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            QMessageBox.warning(self, "Missing file", f"File not found: {token}")
            return

        # Ensure active project is set based on path.
        project_id = self._infer_project_id_from_path(abs_path)
        if project_id:
            self._selected_project_id = project_id
            self._db.set_active_project_id(project_id=project_id)

        text = read_text(abs_path)
        self._open_doc = _OpenDoc(abs_path=abs_path, rel_path=token, original_text=text)
        self.doc_path_label.setText(token)
        self.editor.setPlainText(text)

    def _on_tree_selection_changed(self) -> None:
        # Enable/disable add controls based on selection.
        item = self.tree.currentItem()
        ok = self._get_target_dir_for_new_item(item) is not None
        self._new_file_btn.setEnabled(ok)
        self._new_folder_btn.setEnabled(ok)

    def _reload_open_document(self) -> None:
        if self._open_doc is None:
            return
        if not self._open_doc.abs_path.exists():
            QMessageBox.warning(self, "Missing file", "The file no longer exists on disk.")
            return

        text = read_text(self._open_doc.abs_path)
        self._open_doc = _OpenDoc(
            abs_path=self._open_doc.abs_path,
            rel_path=self._open_doc.rel_path,
            original_text=text,
        )
        self.editor.setPlainText(text)

    def _on_save_document(self) -> None:
        if self._open_doc is None:
            QMessageBox.information(self, "No document", "Select a KB page first.")
            return

        new_text = self.editor.toPlainText()
        old_text = self._open_doc.original_text

        if new_text == old_text:
            QMessageBox.information(self, "No changes", "No changes to save.")
            return

        diff = "\n".join(
            difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=self._open_doc.rel_path,
                tofile=self._open_doc.rel_path,
                lineterm="",
            )
        )

        dlg = _DiffConfirmDialog(
            parent=self,
            title=f"Apply changes: {self._open_doc.rel_path}",
            diff_text=diff,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._open_doc.abs_path.write_text(new_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Write failed", str(exc))
            return

        # Refresh snapshot.
        self._open_doc = _OpenDoc(
            abs_path=self._open_doc.abs_path,
            rel_path=self._open_doc.rel_path,
            original_text=new_text,
        )
        QMessageBox.information(self, "Saved", "Changes written to disk (ready to commit).")

    def _on_link_repo(self) -> None:
        if self._selected_project_id is None:
            QMessageBox.information(self, "No project", "Select a project first.")
            return

        paths = get_project_paths(self._selected_project_id)
        paths.kb_dir.mkdir(parents=True, exist_ok=True)

        repo_dir = QFileDialog.getExistingDirectory(self, "Select local repoPath")
        if not repo_dir:
            return

        settings_text = read_text(paths.settings_md) if paths.settings_md.exists() else "# Settings\n\n"
        current = extract_repo_path(settings_text)

        if current == repo_dir:
            QMessageBox.information(self, "No change", "repoPath unchanged.")
            return

        lines = settings_text.splitlines()
        out: list[str] = []
        replaced = False
        for line in lines:
            if line.strip().startswith("repoPath:"):
                out.append(f"repoPath: {repo_dir}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            if out and out[-1].strip():
                out.append("")
            out.append(f"repoPath: {repo_dir}")

        new_text = "\n".join(out) + "\n"

        diff = "\n".join(
            difflib.unified_diff(
                settings_text.splitlines(),
                new_text.splitlines(),
                fromfile=str(paths.settings_md.relative_to(workspace_root())),
                tofile=str(paths.settings_md.relative_to(workspace_root())),
                lineterm="",
            )
        )

        dlg = _DiffConfirmDialog(
            parent=self,
            title="Update settings.md (repoPath)",
            diff_text=diff,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            paths.settings_md.write_text(new_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Write failed", str(exc))
            return

        if self._open_doc and self._open_doc.abs_path == paths.settings_md:
            self._reload_open_document()

        QMessageBox.information(self, "Updated", "repoPath saved to settings.md.")

    def _infer_project_id_from_path(self, abs_path: Path) -> str | None:
        """Infer project id from an on-disk path under projects/<id>/."""

        try:
            rel = abs_path.relative_to(projects_root())
        except Exception:
            return None
        parts = rel.parts
        if len(parts) >= 2 and parts[0] and is_valid_project_id(parts[0]):
            return parts[0]
        return None

    def _snapshot_expanded_nodes(self) -> set[str]:
        """Return a set of rel-path tokens for expanded dir/project nodes."""

        out: set[str] = set()

        def walk(item: QTreeWidgetItem) -> None:
            kind = item.data(0, _KIND_ROLE)
            token = item.data(0, _PATH_ROLE)
            if item.isExpanded() and isinstance(token, str) and token and kind in {"project", "dir"}:
                out.add(f"{kind}:{token}")
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _restore_expanded_nodes(self, expanded: set[str]) -> None:
        def walk(item: QTreeWidgetItem) -> None:
            kind = item.data(0, _KIND_ROLE)
            token = item.data(0, _PATH_ROLE)
            key = f"{kind}:{token}" if isinstance(kind, str) and isinstance(token, str) else None
            if key and key in expanded:
                item.setExpanded(True)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _select_project(self, project_id: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.data(0, _KIND_ROLE) == "project" and it.data(0, _PATH_ROLE) == project_id:
                self.tree.setCurrentItem(it)
                it.setExpanded(True)
                self._selected_project_id = project_id
                self._db.set_active_project_id(project_id=project_id)
                return

    def _select_by_rel_path(self, rel_path: str) -> None:
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, _KIND_ROLE) == "file" and item.data(0, _PATH_ROLE) == rel_path:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(i))
            if found is not None:
                self.tree.setCurrentItem(found)
                return

    def _get_target_dir_for_new_item(self, item: QTreeWidgetItem | None) -> Path | None:
        if item is None:
            return None

        kind = item.data(0, _KIND_ROLE)
        token = item.data(0, _PATH_ROLE)

        if kind == "project" and isinstance(token, str) and token:
            paths = get_project_paths(token)
            return paths.pages_dir

        if not isinstance(token, str) or not token:
            return None

        abs_path = (workspace_root() / token).resolve()
        if kind == "file":
            return abs_path.parent
        if kind == "dir":
            return abs_path
        return None

    def _on_new_folder(self) -> None:
        item = self.tree.currentItem()
        target_dir = self._get_target_dir_for_new_item(item)
        if target_dir is None:
            QMessageBox.information(self, "No target", "Select a project or folder in the tree first.")
            return

        try:
            name = _safe_name(self._new_item_name.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid name", str(exc))
            return

        new_dir = (target_dir / name).resolve()
        # Restrict to workspace.
        try:
            new_dir.relative_to(workspace_root())
        except Exception:
            QMessageBox.warning(self, "Invalid location", "Folder must be under the workspace.")
            return

        if new_dir.exists():
            QMessageBox.information(self, "Exists", "That folder already exists.")
            return

        try:
            new_dir.mkdir(parents=True, exist_ok=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Create failed", str(exc))
            return

        self._new_item_name.clear()
        self.refresh()

    def _on_new_file(self) -> None:
        item = self.tree.currentItem()
        target_dir = self._get_target_dir_for_new_item(item)
        if target_dir is None:
            QMessageBox.information(self, "No target", "Select a project or folder in the tree first.")
            return

        try:
            name = _safe_name(self._new_item_name.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid name", str(exc))
            return

        if not name.lower().endswith(".md") and not name.lower().endswith(".markdown"):
            # Keep creation scoped to markdown pages by default.
            QMessageBox.warning(self, "Invalid name", "New files must be .md (or .markdown).")
            return

        new_file = (target_dir / name).resolve()
        try:
            new_file.relative_to(workspace_root())
        except Exception:
            QMessageBox.warning(self, "Invalid location", "File must be under the workspace.")
            return

        if new_file.exists():
            QMessageBox.information(self, "Exists", "That file already exists.")
            return

        # Create with an explicit preview.
        rel = _rel_to_workspace(new_file)
        new_text = "# New Page\n\n"
        diff = "\n".join(
            difflib.unified_diff(
                [],
                new_text.splitlines(),
                fromfile=rel,
                tofile=rel,
                lineterm="",
            )
        )

        dlg = _DiffConfirmDialog(parent=self, title=f"Create file: {rel}", diff_text=diff)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.write_text(new_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Create failed", str(exc))
            return

        self._new_item_name.clear()
        self.refresh()
