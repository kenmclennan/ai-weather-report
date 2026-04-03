"""Config screen - view and edit settings in-app."""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from ai_weather_report.config import (
    GENERAL_DEFAULTS, LLM_DEFAULTS, TTS_DEFAULTS,
    load_config, save_config,
)


class ConfigField(Vertical):
    """A label + input pair for a config value."""

    DEFAULT_CSS = """
    ConfigField {
        height: auto;
        margin: 0 0 1 0;
    }
    ConfigField Label {
        color: $text-muted;
        padding: 0 0 0 1;
    }
    ConfigField Input {
        margin: 0 0 0 1;
    }
    """

    def __init__(self, section: str, key: str, label: str,
                 value: str = "", password: bool = False) -> None:
        super().__init__()
        self.section = section
        self.key = key
        self._label = label
        self._value = value
        self._password = password

    def compose(self) -> ComposeResult:
        yield Label(self._label)
        yield Input(
            value=self._value,
            password=self._password,
            id=f"cfg-{self.section}-{self.key}",
        )


class ConfigScreen(Screen):
    """Full-screen config editor."""

    BINDINGS = [
        Binding("escape", "back", "Back (saves)"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._fields: list[ConfigField] = []

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]AI Weather Report[/b]  [dim]- Config[/dim]",
            id="config-header",
        )
        with Center():
            with VerticalScroll(id="config-scroll"):
                yield Static("LLM", id="config-section-llm", classes="config-section-title")
                for key, default in LLM_DEFAULTS.items():
                    val = self._config.get("llm", key, fallback=default)
                    label = key.replace("_", " ").title()
                    is_secret = key == "api_key"
                    field = ConfigField("llm", key, label, val, password=is_secret)
                    self._fields.append(field)
                    yield field

                yield Static("", classes="config-spacer")
                yield Static("TTS", id="config-section-tts", classes="config-section-title")
                for key, default in TTS_DEFAULTS.items():
                    val = self._config.get("tts", key, fallback=default)
                    label = key.replace("_", " ").title()
                    is_secret = key == "api_key"
                    field = ConfigField("tts", key, label, val, password=is_secret)
                    self._fields.append(field)
                    yield field

                yield Static("", classes="config-spacer")
                yield Static("General", id="config-section-general", classes="config-section-title")
                for key, default in GENERAL_DEFAULTS.items():
                    val = self._config.get("general", key, fallback=default)
                    label = key.replace("_", " ").title()
                    field = ConfigField("general", key, label, val)
                    self._fields.append(field)
                    yield field

                yield Static("", classes="config-spacer")
                yield Static("Feeds", id="config-section-feeds", classes="config-section-title")
                yield Static(
                    "One feed per line:  Name = URL",
                    classes="config-help",
                )
                feeds_text = ""
                if self._config.has_section("feeds"):
                    feeds_text = "\n".join(
                        f"{name} = {url}"
                        for name, url in self._config.items("feeds")
                    )
                yield Input(
                    value=feeds_text,
                    id="cfg-feeds-all",
                )
                yield Static(
                    "[dim]Edit feeds directly in ~/.ai-weather-report/config.ini for multi-line editing[/dim]",
                    classes="config-help",
                )

        yield Static("", id="config-status", markup=False)
        yield Static(" Tab/Shift+Tab  Navigate    Esc  Save and back    q  Quit", id="config-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#config-status").display = False
        # Focus the first input
        if self._fields:
            first_input = self._fields[0].query_one(Input)
            first_input.focus()

    def _save(self) -> None:
        """Save all field values back to config."""
        config = self._config

        for field in self._fields:
            inp = field.query_one(Input)
            if not config.has_section(field.section):
                config.add_section(field.section)
            config.set(field.section, field.key, inp.value)

        # Save feeds from the single input
        feeds_input = self.query_one("#cfg-feeds-all", Input)
        if config.has_section("feeds"):
            config.remove_section("feeds")
        config.add_section("feeds")
        for line in feeds_input.value.split("\n"):
            line = line.strip()
            if "=" in line:
                name, url = line.split("=", 1)
                name = name.strip()
                url = url.strip()
                if name and url:
                    config.set("feeds", name, url)

        save_config(config)

    def action_back(self) -> None:
        self._save()
        self.app.pop_screen()
