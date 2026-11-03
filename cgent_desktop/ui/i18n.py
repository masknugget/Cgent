"""Translatable source strings for session history actions."""

from PySide6.QtCore import QCoreApplication

_CONTEXT = "SessionHistory"

COPY_TITLE = "复制会话标题"
RENAME = "重命名"
RETRY = "重新运行"
DELETE = "删除"
CANCEL = "取消"
NEW_SESSION = "新建会话"
UNNAMED_SESSION = "未命名会话"
DELETE_TITLE = "删除会话"
DELETE_CONTENT = "删除后不可恢复，确定删除该会话吗？"
DELETE_SUCCESS_TITLE = "会话已删除"
DELETE_ERROR_TITLE = "删除失败"
DELETE_ERROR_CONTENT = "无法删除该会话，请稍后重试。"
RENAME_ERROR_TITLE = "重命名失败"
RENAME_ERROR_CONTENT = "无法保存会话标题，请稍后重试。"
EMPTY_HISTORY = "暂无历史会话"
NO_MATCHING_HISTORY = "没有匹配的会话"

WORKSPACE_TITLE = "工作目录"
REFRESH = "刷新"
COLLAPSE_ALL = "全部收起"
COLLAPSE_PANEL = "折叠面板"
SEARCH_FILES = "搜索文件…"
SHOW_IN_FILE_MANAGER = "在文件管理器中显示"
COPY_PATH = "复制路径"
INVALID_WORKSPACE = "工作目录不存在或不可访问"
SELECT_WORKSPACE = "选择工作目录"
CHOOSE_WORKSPACE = "选择工作目录"


def tr(source_text: str) -> str:
    return QCoreApplication.translate(_CONTEXT, source_text)


def tr_workspace(source_text: str) -> str:
    return QCoreApplication.translate("WorkspacePanel", source_text)
