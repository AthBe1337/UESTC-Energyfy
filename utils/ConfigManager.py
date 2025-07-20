import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import (
    Button,
    Input,
    Label,
    ListView,
    ListItem,
    Select,
    Static,
    TextArea,
)
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual import on, events, work


class ConfigManager:
    """配置管理核心类，处理文件操作"""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}

    def load_config(self) -> bool:
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                return True
            return False
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载配置文件错误: {e}")
            return False

    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"保存配置文件错误: {e}")
            return False

    def generate_default_config(self) -> Dict[str, Any]:
        """生成默认配置"""
        return {
            "username": "",
            "password": "",
            "check_interval": 600,
            "alert_balance": 10,
            "smtp": {
                "server": "",
                "port": 465,
                "username": "",
                "password": "",
                "security": "ssl",
            },
            "queries": [],
        }


class EditItemScreen(ModalScreen):
    """编辑单个项目的模态窗口"""

    def __init__(self, item: Any, item_type: type, key: str = "", parent_key: str = ""):
        super().__init__()
        self.item = item
        self.item_type = item_type
        self.key = key
        self.parent_key = parent_key
        self.is_new = False

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label(f"编辑 {self.key}" if self.key else "编辑项目")
            if self.item_type in (str, int, float, bool):
                if isinstance(self.item, bool):
                    current_value = str(self.item)
                    yield Select(
                        [(str(True), "True"), (str(False), "False")],
                        value=current_value,
                        id="value-input",
                    )
                else:
                    yield Input(str(self.item), id="value-input")
            elif self.item_type == dict:
                text = json.dumps(self.item, indent=2, ensure_ascii=False)
                yield TextArea(text, id="value-input", language="json")
            elif self.item_type == list:
                text = json.dumps(self.item, indent=2, ensure_ascii=False)
                yield TextArea(text, id="value-input", language="json")

            with Horizontal():
                yield Button("保存", id="save")
                yield Button("取消", id="cancel")

    @on(Button.Pressed, "#save")
    def save_item(self):
        input_widget = self.query_one("#value-input")
        if isinstance(input_widget, Input):
            value = input_widget.value
            if self.item_type == int:
                value = int(value)
            elif self.item_type == float:
                value = float(value)
            elif self.item_type == bool:
                value = value.lower() == "true"
        elif isinstance(input_widget, Select):
            value = input_widget.value == "True"
        elif isinstance(input_widget, TextArea):
            try:
                value = json.loads(input_widget.text)
            except json.JSONDecodeError:
                self.notify("无效的JSON格式", severity="error")
                return

        self.dismiss((self.key, value, self.parent_key, self.is_new))

    @on(Button.Pressed, "#cancel")
    def cancel_edit(self):
        self.dismiss(None)


class ArrayEditScreen(ModalScreen):
    """编辑数组的模态窗口"""

    def __init__(self, items: List[Any], item_type: type, key: str = ""):
        super().__init__()
        self.items = items
        self.item_type = item_type
        self.key = key

    def compose(self) -> ComposeResult:
        with Container(id="array-dialog"):
            yield Label(f"编辑 {self.key}" if self.key else "编辑数组")
            yield ListView(id="array-list")
            with Horizontal():
                yield Button("添加", id="add")
                yield Button("编辑", id="edit")
                yield Button("删除", id="delete")
                yield Button("完成", id="done")

    def on_mount(self) -> None:
        self.update_list()

    def update_list(self) -> None:
        list_view = self.query_one("#array-list")
        list_view.clear()
        for i, item in enumerate(self.items):
            if isinstance(item, (dict, list)):
                text = json.dumps(item, indent=2, ensure_ascii=False)
                if len(text) > 50:
                    text = text[:50] + "..."
            else:
                text = str(item)
            list_view.append(ListItem(Label(f"{i}: {text}")))

    @on(Button.Pressed, "#add")
    def add_item(self):
        if self.item_type == dict:
            new_item = {}
        elif self.item_type == list:
            new_item = []
        else:
            new_item = self.item_type()

        self.app.push_screen(
            EditItemScreen(new_item, self.item_type, "", self.key),
            self.handle_edit_result,
        )

    @on(Button.Pressed, "#edit")
    async def edit_item(self):
        list_view = self.query_one("#array-list")
        if list_view.index is not None:
            index = list_view.index
            item = self.items[index]
            await self.app.push_screen(
                EditItemScreen(item, self.item_type, str(index),
                               self.handle_edit_result
                               )

                @ on(Button.Pressed, "#delete")
            )

    def delete_item(self):
        list_view = self.query_one("#array-list")
        if list_view.index is not None:
            index = list_view.index
            del self.items[index]
            self.update_list()

    @on(Button.Pressed, "#done")
    def done_editing(self):
        self.dismiss(self.items)

    def handle_edit_result(self, result):
        if result is None:
            return

        key, value, parent_key, is_new = result
        if parent_key == self.key:  # 这是数组元素
            if key:  # 编辑现有元素
                index = int(key)
                self.items[index] = value
            else:  # 添加新元素
                self.items.append(value)
            self.update_list()


class ConfigEditor(App):
    """配置编辑器主应用"""

    CSS_PATH = "./css/config_editor.css"
    BINDINGS = [
        ("ctrl+s", "save_config", "保存"),
        ("ctrl+q", "quit", "退出"),
    ]

    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.manager = ConfigManager(config_path)
        if not self.manager.load_config():
            self.manager.config = self.manager.generate_default_config()

    def compose(self) -> ComposeResult:
        yield Label("配置编辑器", id="title")
        with Vertical(id="config-container"):
            yield Label("基本配置", classes="section-title")
            with Vertical(classes="section"):
                yield from self.create_input_fields(self.manager.config, exclude=["smtp", "queries"])

            yield Label("SMTP配置", classes="section-title")
            with Vertical(classes="section"):
                yield from self.create_input_fields(self.manager.config["smtp"], parent_key="smtp")

            yield Label("查询配置", classes="section-title")
            with Vertical(classes="section"):
                yield Button("编辑查询列表", id="edit-queries")

        with Horizontal(id="buttons"):
            yield Button("保存", id="save")
            yield Button("重新加载", id="reload")
            yield Button("退出", id="quit")

    def create_input_fields(self, config: Dict[str, Any], parent_key: str = "",
                            exclude: List[str] = []) -> ComposeResult:
        """为配置字典创建输入字段"""
        for key, value in config.items():
            if key in exclude:
                continue

            if isinstance(value, (str, int, float)):
                yield Label(key)
                yield Input(str(value), id=f"{parent_key}.{key}" if parent_key else key)
            elif isinstance(value, bool):
                yield Label(key)
                yield Select(
                    [(str(True), "True"), (str(False), "False")],
                    value=str(value),
                    id=f"{parent_key}.{key}" if parent_key else key,
                )
            elif isinstance(value, dict):
                yield Label(key)
                yield Button("编辑", id=f"edit-{parent_key}.{key}" if parent_key else f"edit-{key}")
            elif isinstance(value, list):
                yield Label(key)
                yield Button("编辑", id=f"edit-{parent_key}.{key}" if parent_key else f"edit-{key}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.save_config()
        elif event.button.id == "reload":
            self.manager.load_config()
            self.notify("配置已重新加载", timeout=3)
        elif event.button.id == "quit":
            self.exit()
        elif event.button.id == "edit-queries":
            await self.edit_queries()
        elif event.button.id.startswith("edit-"):
            key = event.button.id[5:]  # 去掉"edit-"前缀
            await self.edit_complex_value(key)

    async def edit_complex_value(self, key: str):
        """编辑复杂值(字典或数组)"""
        keys = key.split(".")
        current = self.manager.config
        for k in keys[:-1]:
            current = current[k]

        value = current[keys[-1]]
        if isinstance(value, dict):
            await self.edit_dict_value(value, key)
        elif isinstance(value, list):
            await self.edit_array_value(value, key)

    async def edit_dict_value(self, value: Dict[str, Any], key: str):
        """编辑字典值"""
        result = await self.push_screen_wait(EditItemScreen(value, dict, key))
        if result is not None:
            _, new_value, full_key, _ = result
            keys = full_key.split(".")
            current = self.manager.config
            for k in keys[:-1]:
                current = current[k]
            current[keys[-1]] = new_value

    async def edit_array_value(self, value: List[Any], key: str):
        """编辑数组值"""
        if value and isinstance(value[0], dict):
            item_type = dict
        elif value and isinstance(value[0], list):
            item_type = list
        else:
            item_type = type(value[0]) if value else str

        result = await self.push_screen_wait(ArrayEditScreen(value, item_type, key))
        if result is not None:
            keys = key.split(".")
            current = self.manager.config
            for k in keys[:-1]:
                current = current[k]
            current[keys[-1]] = result

    async def edit_queries(self):
        """编辑查询列表"""
        queries = self.manager.config["queries"]
        result = await self.push_screen_wait(ArrayEditScreen(queries, dict, "queries"))
        if result is not None:
            self.manager.config["queries"] = result

    def save_config(self):
        """保存配置"""
        # 更新简单值
        for input_widget in self.query(Input):
            key = input_widget.id
            keys = key.split(".")
            current = self.manager.config
            for k in keys[:-1]:
                current = current[k]
            value = input_widget.value
            if isinstance(current[keys[-1]], int):
                value = int(value)
            elif isinstance(current[keys[-1]], float):
                value = float(value)
            current[keys[-1]] = value

        # 更新布尔值
        for select_widget in self.query(Select):
            key = select_widget.id
            keys = key.split(".")
            current = self.manager.config
            for k in keys[:-1]:
                current = current[k]
            current[keys[-1]] = select_widget.value == "True"

        if self.manager.save_config():
            self.notify("配置已保存", timeout=3)
        else:
            self.notify("保存配置失败", severity="error")

    def action_save_config(self):
        """保存配置的快捷键动作"""
        self.save_config()


if __name__ == "__main__":
    app = ConfigEditor()
    app.run()
