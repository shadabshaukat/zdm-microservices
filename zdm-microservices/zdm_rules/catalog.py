from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised only when dependency is absent.
    raise RuntimeError("PyYAML is required to load ZDM migration profiles") from exc

from zdm_rules.conditions import condition_matches
from zdm_rules.common import normalize_rsp_value


PROFILE_DIR = Path(__file__).resolve().parent / "definitions" / "profiles"
FIELD_CONTROL_TYPES = {"text", "select", "number", "wallet", "metadata_remaps", "include_schemas"}
JOB_RUN_CONTROL_TYPES = {"checkbox", "multiselect", "schedule", "select", "text", "textarea"}
JOB_RUN_CONTROL_KEYS = {
    "advisor_mode",
    "flow_control",
    "flow_phase",
    "genfixup",
    "ignore",
    "schedule",
    "listphases",
    "custom_args",
}
JOB_RUN_CONTROL_CONFIG_KEYS = {
    "control",
    "default",
    "help",
    "label",
    "now_label",
    "now_value",
    "options",
    "text_help",
    "text_label",
}
RULE_GROUP_FAMILIES = {"logical", "physical"}
RULE_GROUP_ROLES = {"source", "target"}
RESPONSE_FILE_KEYS = {
    "additional_parameters",
    "default_medium",
    "derived_fields",
    "fields",
    "media",
    "platform_mediums",
    "sections",
    "ui",
    "validation",
}
JOB_SUBMISSION_KEYS = {"fields", "run_controls", "run_defaults", "sections"}
PROFILE_KEYS = {"method", "migration_type", "decision_inputs", "response_file", "job_submission"}


@dataclass(frozen=True)
class MediumOption:
    value: str
    enabled: bool


class MigrationProfile:
    def __init__(self, data: Mapping[str, Any], path: Path):
        self.data = dict(data)
        self.path = path
        self.method = normalize_method(self.data.get("method"))
        if not self.method:
            raise ValueError(f"{path} is missing method")
        if not isinstance(self.fields, Mapping) or not self.fields:
            raise ValueError(f"{path} is missing fields")
        if not isinstance(self.media, Mapping) or not self.media:
            raise ValueError(f"{path} is missing media")
        if not isinstance(self.validation, Mapping) or not self.validation:
            raise ValueError(f"{path} is missing validation")
        self._validate_schema()

    @property
    def migration_type(self) -> str:
        return str(self.data.get("migration_type") or "")

    @property
    def default_medium(self) -> str:
        return normalize_method(self._response_file_config().get("default_medium")) or self.medium_keys()[0]

    @property
    def fields(self) -> Mapping[str, Mapping[str, Any]]:
        fields = self._response_file_config().get("fields") or {}
        if not isinstance(fields, Mapping):
            return {}
        return {
            str(key): value if isinstance(value, Mapping) else {}
            for key, value in fields.items()
        }

    @property
    def media(self) -> Mapping[str, Mapping[str, Any]]:
        media = self._response_file_config().get("media") or {}
        return media if isinstance(media, Mapping) else {}

    def field(self, key: str) -> Mapping[str, Any]:
        return self.fields.get(str(key), {})

    def _validate_schema(self) -> None:
        unknown_profile_keys = sorted(str(key) for key in self.data.keys() if str(key) not in PROFILE_KEYS)
        if unknown_profile_keys:
            raise ValueError(
                f"{self.path} profile has invalid keys: "
                + ", ".join(unknown_profile_keys)
            )

        self._validate_decision_inputs_config()

        response_file = self.data.get("response_file")
        if not isinstance(response_file, Mapping):
            raise ValueError(f"{self.path} response_file must be a mapping")
        unknown_response_file_keys = sorted(str(key) for key in response_file.keys() if str(key) not in RESPONSE_FILE_KEYS)
        if unknown_response_file_keys:
            raise ValueError(
                f"{self.path} response_file has invalid keys: "
                + ", ".join(unknown_response_file_keys)
            )

        fields = response_file.get("fields")
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError(f"{self.path} response_file.fields must be a non-empty mapping")
        for key, config in fields.items():
            if not str(key).strip():
                raise ValueError(f"{self.path} response_file.fields contains a blank field key")
            if not isinstance(config, Mapping):
                raise ValueError(f"{self.path} response_file.fields.{key} must be a mapping")
            self._validate_response_field_config(str(key), config)

        field_keys = {str(key) for key in fields.keys()}
        derived_fields = response_file.get("derived_fields") or []
        if derived_fields:
            derived_fields = _field_list(derived_fields, f"{self.path} response_file.derived_fields")
            overlap = sorted(set(derived_fields) & field_keys)
            if overlap:
                raise ValueError(
                    f"{self.path} response_file.derived_fields duplicates editable fields: "
                    + ", ".join(overlap)
                )

        sections = response_file.get("sections")
        if not isinstance(sections, Mapping) or not sections:
            raise ValueError(f"{self.path} response_file.sections must be a non-empty mapping")
        _validate_section_references(self.path, "response_file.sections", sections, field_keys)
        section_keys = {str(key) for key in sections.keys()}

        ui = response_file.get("ui")
        if not isinstance(ui, Mapping) or not ui:
            raise ValueError(f"{self.path} response_file.ui must be a non-empty mapping")
        self._validate_response_ui(ui, section_keys)

        media = response_file.get("media")
        if not isinstance(media, Mapping) or not media:
            raise ValueError(f"{self.path} response_file.media must be a non-empty mapping")
        default_medium = normalize_method(response_file.get("default_medium"))
        if not default_medium or default_medium not in {normalize_method(key) for key in media.keys()}:
            raise ValueError(f"{self.path} response_file.default_medium must reference a configured medium")
        for medium_key, config in media.items():
            if not isinstance(config, Mapping):
                raise ValueError(f"{self.path} response_file.media.{medium_key} must be a mapping")
            medium_fields = _field_list(config.get("fields"), f"{self.path} response_file.media.{medium_key}.fields")
            medium_advanced = _field_list(
                config.get("advanced_fields") or [],
                f"{self.path} response_file.media.{medium_key}.advanced_fields",
            )
            _validate_known_fields(
                self.path,
                f"response_file.media.{medium_key}",
                medium_fields + medium_advanced,
                field_keys,
            )
            medium_sections = config.get("sections") or {}
            if medium_sections:
                if not isinstance(medium_sections, Mapping):
                    raise ValueError(f"{self.path} response_file.media.{medium_key}.sections must be a mapping")
                self._validate_response_ui_section_labels(
                    f"response_file.media.{medium_key}.sections",
                    {str(key) for key in medium_sections.keys()},
                )
                medium_section_fields = _section_field_refs(
                    medium_sections,
                    f"{self.path} response_file.media.{medium_key}.sections",
                )
                _validate_known_fields(
                    self.path,
                    f"response_file.media.{medium_key}.sections",
                    medium_section_fields,
                    set(medium_fields + medium_advanced),
                )

        platform_mediums = response_file.get("platform_mediums") or {}
        if platform_mediums:
            if not isinstance(platform_mediums, Mapping):
                raise ValueError(f"{self.path} response_file.platform_mediums must be a mapping")
            medium_keys = {normalize_method(key) for key in media.keys()}
            for platform, medium_values in platform_mediums.items():
                medium_refs = _field_list(
                    medium_values,
                    f"{self.path} response_file.platform_mediums.{platform}",
                )
                unknown = sorted(
                    value for value in medium_refs if normalize_method(value) not in medium_keys
                )
                if unknown:
                    raise ValueError(
                        f"{self.path} response_file.platform_mediums.{platform} references unknown media: "
                        + ", ".join(unknown)
                    )

        validation = response_file.get("validation")
        if not isinstance(validation, Mapping) or not validation:
            raise ValueError(f"{self.path} response_file.validation must be a non-empty mapping")
        self._validate_response_validation_rules(validation)

        job_submission = self.data.get("job_submission")
        if not isinstance(job_submission, Mapping) or not job_submission:
            raise ValueError(f"{self.path} job_submission must be a non-empty mapping")
        unknown_job_submission_keys = sorted(
            str(key) for key in job_submission.keys() if str(key) not in JOB_SUBMISSION_KEYS
        )
        if unknown_job_submission_keys:
            raise ValueError(
                f"{self.path} job_submission has invalid keys: "
                + ", ".join(unknown_job_submission_keys)
            )
        job_fields = _field_list(job_submission.get("fields"), f"{self.path} job_submission.fields")
        job_field_keys = set(job_fields)
        job_sections = job_submission.get("sections")
        if not isinstance(job_sections, Mapping) or not job_sections:
            raise ValueError(f"{self.path} job_submission.sections must be a non-empty mapping")
        _validate_section_references(self.path, "job_submission.sections", job_sections, job_field_keys)
        self._validate_job_run_controls(job_submission)
        run_defaults = job_submission.get("run_defaults") or {}
        if run_defaults:
            if not isinstance(run_defaults, Mapping):
                raise ValueError(f"{self.path} job_submission.run_defaults must be a mapping")
            medium_keys = {normalize_method(key) for key in media.keys()}
            for medium_key, defaults in run_defaults.items():
                if normalize_method(medium_key) not in medium_keys:
                    raise ValueError(
                        f"{self.path} job_submission.run_defaults references unknown medium: {medium_key}"
                    )
                if not isinstance(defaults, Mapping):
                    raise ValueError(f"{self.path} job_submission.run_defaults.{medium_key} must be a mapping")
                for run_type, values in defaults.items():
                    if normalize_method(run_type) not in {"EVAL", "MIGRATE"}:
                        raise ValueError(
                            f"{self.path} job_submission.run_defaults.{medium_key} has invalid run type: {run_type}"
                        )
                    if not isinstance(values, Mapping):
                        raise ValueError(
                            f"{self.path} job_submission.run_defaults.{medium_key}.{run_type} must be a mapping"
                        )

    def _validate_job_run_controls(self, job_submission: Mapping[str, Any]) -> None:
        run_controls = job_submission.get("run_controls")
        if not isinstance(run_controls, Mapping) or not run_controls:
            raise ValueError(f"{self.path} job_submission.run_controls must be a non-empty mapping")

        unknown_controls = sorted(str(key) for key in run_controls.keys() if str(key) not in JOB_RUN_CONTROL_KEYS)
        if unknown_controls:
            raise ValueError(
                f"{self.path} job_submission.run_controls has invalid controls: "
                + ", ".join(unknown_controls)
            )

        for name, config in run_controls.items():
            if not isinstance(config, Mapping):
                raise ValueError(f"{self.path} job_submission.run_controls.{name} must be a mapping")
            unknown_keys = sorted(str(key) for key in config.keys() if str(key) not in JOB_RUN_CONTROL_CONFIG_KEYS)
            if unknown_keys:
                raise ValueError(
                    f"{self.path} job_submission.run_controls.{name} has invalid keys: "
                    + ", ".join(unknown_keys)
                )
            control = str(config.get("control") or "text")
            if control not in JOB_RUN_CONTROL_TYPES:
                raise ValueError(
                    f"{self.path} job_submission.run_controls.{name}.control has invalid value: {control}"
                )
            label = config.get("label")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"{self.path} job_submission.run_controls.{name}.label must be a non-empty string")
            if control in {"select", "multiselect"}:
                options = config.get("options")
                if not isinstance(options, list) or not options:
                    raise ValueError(
                        f"{self.path} job_submission.run_controls.{name}.options must be a non-empty list"
                    )
                option_values = [str(option) for option in options]
                if any(option is None for option in options):
                    raise ValueError(
                        f"{self.path} job_submission.run_controls.{name}.options must not contain null values"
                    )
                default = config.get("default")
                if control == "select" and default is not None and str(default) not in option_values:
                    raise ValueError(
                        f"{self.path} job_submission.run_controls.{name}.default must be listed in options"
                    )
            if control == "checkbox" and "default" in config and not isinstance(config.get("default"), bool):
                raise ValueError(f"{self.path} job_submission.run_controls.{name}.default must be a boolean")

    def _validate_response_validation_rules(self, validation: Mapping[str, Any]) -> None:
        defaults = validation.get("defaults") or {}
        if defaults and not isinstance(defaults, Mapping):
            raise ValueError(f"{self.path} response_file.validation.defaults must be a mapping")

        allowed = set(self.all_response_field_keys())
        allowed.update({"project", "filename"})
        _validate_known_fields(
            self.path,
            "response_file.validation.defaults",
            [str(key) for key in defaults.keys()],
            allowed,
        )

        required = validation.get("required") or []
        if required and not isinstance(required, list):
            raise ValueError(f"{self.path} response_file.validation.required must be a list")
        for index, rule in enumerate(required, start=1):
            if not isinstance(rule, Mapping):
                raise ValueError(f"{self.path} response_file.validation.required[{index}] must be a mapping")
            if "one_of" in rule:
                one_of = _field_list(
                    rule.get("one_of"),
                    f"{self.path} response_file.validation.required[{index}].one_of",
                )
                _validate_known_fields(
                    self.path,
                    f"response_file.validation.required[{index}].one_of",
                    one_of,
                    allowed,
                )
                continue
            key = str(rule.get("key") or "")
            if not key:
                raise ValueError(f"{self.path} response_file.validation.required[{index}] is missing key")
            _validate_known_fields(
                self.path,
                f"response_file.validation.required[{index}]",
                [key],
                allowed,
            )

    def _validate_decision_inputs_config(self) -> None:
        decision_inputs = self.data.get("decision_inputs") or {}
        if not decision_inputs:
            return
        if not isinstance(decision_inputs, Mapping):
            raise ValueError(f"{self.path} decision_inputs must be a mapping")
        controls = decision_inputs.get("controls")
        if not isinstance(controls, Mapping) or not controls:
            raise ValueError(f"{self.path} decision_inputs.controls must be a non-empty mapping")
        for name, config in controls.items():
            if not str(name).strip():
                raise ValueError(f"{self.path} decision_inputs.controls contains a blank control name")
            if not isinstance(config, Mapping):
                raise ValueError(f"{self.path} decision_inputs.controls.{name} must be a mapping")
            options = config.get("options")
            if not isinstance(options, list) or not options:
                raise ValueError(f"{self.path} decision_inputs.controls.{name}.options must be a non-empty list")
            option_values = [str(value) for value in options]
            if any(not value.strip() for value in option_values):
                raise ValueError(f"{self.path} decision_inputs.controls.{name}.options must not contain blank values")
            default = config.get("default")
            if default is not None and str(default) not in option_values:
                raise ValueError(f"{self.path} decision_inputs.controls.{name}.default must be listed in options")
            rule_group_ref = config.get("from_rule_group")
            if rule_group_ref is None:
                continue
            parts = str(rule_group_ref).split(".")
            if len(parts) != 2 or parts[0] not in RULE_GROUP_FAMILIES or parts[1] not in RULE_GROUP_ROLES:
                raise ValueError(
                    f"{self.path} decision_inputs.controls.{name}.from_rule_group must use <logical|physical>.<source|target>"
                )

    def _validate_response_field_config(self, key: str, config: Mapping[str, Any]) -> None:
        control = str(config.get("control") or "text")
        if control not in FIELD_CONTROL_TYPES:
            raise ValueError(
                f"{self.path} response_file.fields.{key}.control has invalid value: {control}"
            )
        if control != "select":
            return
        options = config.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError(
                f"{self.path} response_file.fields.{key}.options must be a non-empty list for select controls"
            )

    def _validate_response_ui(self, ui: Mapping[str, Any], section_keys: set[str]) -> None:
        layout = ui.get("layout")
        if not isinstance(layout, list) or not layout:
            raise ValueError(f"{self.path} response_file.ui.layout must be a non-empty list")
        medium_fields_title = ui.get("medium_fields_title")
        if not isinstance(medium_fields_title, str) or not medium_fields_title.strip():
            raise ValueError(f"{self.path} response_file.ui.medium_fields_title must be a non-empty string")
        section_labels = ui.get("section_labels")
        if not isinstance(section_labels, Mapping):
            raise ValueError(f"{self.path} response_file.ui.section_labels must be a mapping")
        self._validate_response_ui_section_labels("response_file.sections", section_keys)

        for index, item in enumerate(layout, start=1):
            if not isinstance(item, Mapping):
                raise ValueError(f"{self.path} response_file.ui.layout[{index}] must be a mapping")
            item_type = str(item.get("type") or "")
            if item_type not in {"tabs", "sections", "medium", "additional_parameters", "section"}:
                raise ValueError(f"{self.path} response_file.ui.layout has invalid item type: {item_type}")
            if item_type == "tabs":
                _validate_ui_title(self.path, item, f"response_file.ui.layout[{index}]")
                tabs = _field_list(item.get("tabs"), f"{self.path} response_file.ui.layout[{index}].tabs")
                if not tabs:
                    raise ValueError(f"{self.path} response_file.ui.layout[{index}].tabs must not be empty")
                _validate_known_sections(self.path, "response_file.ui.layout", tabs, section_keys)
                continue
            if item_type == "sections":
                _validate_ui_title(self.path, item, f"response_file.ui.layout[{index}]")
                refs = _layout_section_refs(item.get("sections"), f"{self.path} response_file.ui.layout[{index}].sections")
                _validate_known_sections(self.path, "response_file.ui.layout", refs, section_keys)
                continue
            if item_type == "section":
                section = str(item.get("section") or "")
                if not section:
                    raise ValueError(f"{self.path} response_file.ui.layout[{index}].section must be a non-empty string")
                _validate_known_sections(self.path, "response_file.ui.layout", [section], section_keys)
                continue
            if item_type == "additional_parameters":
                _validate_ui_title(self.path, item, f"response_file.ui.layout[{index}]")

    def _validate_response_ui_section_labels(self, label: str, section_keys: set[str]) -> None:
        section_labels = self._response_ui_config().get("section_labels") or {}
        label_keys = {str(key) for key in section_labels.keys()} if isinstance(section_labels, Mapping) else set()
        missing = sorted(key for key in section_keys if key not in label_keys)
        if missing:
            raise ValueError(f"{self.path} response_file.ui.section_labels missing {label}: " + ", ".join(missing))

    def common_response_field_keys(self) -> List[str]:
        sections = self._response_file_config().get("sections") or {}
        return _flatten_field_groups(sections)

    def section_field_keys(self, section: str) -> List[str]:
        sections = self._response_file_config().get("sections") or {}
        if not isinstance(sections, Mapping):
            return []
        value = _nested_section_value(sections, section)
        return _flatten_field_groups(value)

    def common_job_field_keys(self) -> List[str]:
        fields = self._job_submission_config().get("fields") or []
        return [str(value) for value in fields]

    def job_section_field_keys(self, section: str) -> List[str]:
        sections = self._job_submission_config().get("sections") or {}
        if not isinstance(sections, Mapping):
            return []
        value = _nested_section_value(sections, section)
        return _flatten_field_groups(value)

    @property
    def job_run_controls(self) -> Mapping[str, Mapping[str, Any]]:
        controls = self._job_submission_config().get("run_controls") or {}
        if not isinstance(controls, Mapping):
            return {}
        return {
            str(key): value if isinstance(value, Mapping) else {}
            for key, value in controls.items()
        }

    def job_run_control(self, name: str) -> Mapping[str, Any]:
        return self.job_run_controls.get(str(name), {})

    def medium_keys(self) -> List[str]:
        return [str(key) for key in self.media.keys()]

    def medium(self, medium: Any) -> Mapping[str, Any]:
        return self.media.get(normalize_method(medium), {})

    @property
    def decision_input_controls(self) -> Mapping[str, Mapping[str, Any]]:
        controls = (
            self._decision_inputs_config().get("controls")
            or {}
        )
        if not isinstance(controls, Mapping):
            return {}
        return {
            str(key): value if isinstance(value, Mapping) else {}
            for key, value in controls.items()
        }

    def decision_input_control(self, name: str) -> Mapping[str, Any]:
        return self.decision_input_controls.get(str(name), {})

    def medium_field_keys(self, medium: Any, include_advanced: bool = False) -> List[str]:
        config = self.medium(medium)
        keys = [str(key) for key in config.get("fields") or []]
        if include_advanced:
            keys += [str(key) for key in config.get("advanced_fields") or []]
        return keys

    def medium_section_field_keys(self, medium: Any, section: str) -> List[str]:
        config = self.medium(medium)
        sections = config.get("sections") or {}
        if not isinstance(sections, Mapping):
            return []
        value = _nested_section_value(sections, section)
        return _flatten_field_groups(value)

    def medium_section_names(self, medium: Any) -> List[str]:
        config = self.medium(medium)
        sections = config.get("sections") or {}
        if not isinstance(sections, Mapping):
            return []
        return [str(key) for key in sections.keys()]

    def medium_unsectioned_field_keys(self, medium: Any) -> List[str]:
        config = self.medium(medium)
        fields = [str(key) for key in config.get("fields") or []]
        sections = config.get("sections") or {}
        if not isinstance(sections, Mapping) or not sections:
            return fields
        section_fields = set(_section_field_refs(sections, f"{self.path} response_file.media.{medium}.sections"))
        return [key for key in fields if key not in section_fields]

    def response_layout(self) -> List[Dict[str, Any]]:
        ui = self._response_ui_config()
        return [_copy_layout_item(item) for item in ui.get("layout") or [] if isinstance(item, Mapping)]

    def section_label(self, section: str) -> str:
        labels = self._response_ui_config().get("section_labels") or {}
        if isinstance(labels, Mapping) and section in labels:
            return str(labels[section])
        raise ValueError(f"{self.path} response_file.ui.section_labels missing section: {section}")

    def medium_fields_title(self) -> str:
        title = self._response_ui_config().get("medium_fields_title")
        if isinstance(title, str) and title.strip():
            return title
        raise ValueError(f"{self.path} response_file.ui.medium_fields_title must be a non-empty string")

    def all_response_field_keys(self, medium: Any = None, include_advanced: bool = False) -> List[str]:
        keys = ["MIGRATION_METHOD", "DATA_TRANSFER_MEDIUM"]
        keys += self.decision_input_response_field_keys()
        keys += self.derived_response_field_keys()
        keys += self.common_response_field_keys()
        media_to_include = [normalize_method(medium)] if medium else self.medium_keys()
        for medium_key in media_to_include:
            keys += self.medium_field_keys(medium_key, include_advanced=include_advanced)
        keys += ["include_schemas", "DATAPUMPSETTINGS_METADATAREMAPS", "additional"]
        return _unique(keys)

    def derived_response_field_keys(self) -> List[str]:
        values = self._response_file_config().get("derived_fields") or []
        return [str(value) for value in values] if isinstance(values, list) else []

    def decision_input_response_field_keys(self) -> List[str]:
        return self._decision_input_response_keys()

    def platform_medium_keys(self, platform: Any) -> List[str]:
        platform_key = normalize_method(platform)
        platform_mediums = (
            self._response_file_config().get("platform_mediums")
            or {}
        )
        values = platform_mediums.get(platform_key) or []
        return [normalize_method(value) for value in values]

    def medium_options(self, context: Optional[Mapping[str, Any]] = None) -> List[MediumOption]:
        context = dict(context or {})
        allowed_by_platform = self._platform_allowed_mediums(context)
        options: List[MediumOption] = []
        for medium_key, config in self.media.items():
            medium_s = normalize_method(medium_key)
            if allowed_by_platform is not None and medium_s not in allowed_by_platform:
                continue
            enabled = condition_matches(config.get("show_when"), self._condition_context(context))
            options.append(
                MediumOption(
                    value=medium_s,
                    enabled=enabled,
                )
            )
        return options

    def enabled_medium_keys(self, context: Optional[Mapping[str, Any]] = None) -> List[str]:
        return [option.value for option in self.medium_options(context) if option.enabled]

    def run_defaults(self, medium: Any, run_type: Any) -> Dict[str, str]:
        job_defaults = self._job_submission_config().get("run_defaults") or {}
        defaults = {}
        if isinstance(job_defaults, Mapping):
            defaults = job_defaults.get(normalize_method(medium)) or {}
        if not defaults:
            defaults = self.medium(medium).get("run_defaults") or {}
        run_defaults = defaults.get(normalize_method(run_type)) or {}
        return {str(key): str(value) for key, value in run_defaults.items()}

    def additional_default_rows(self) -> List[Dict[str, str]]:
        config = self._response_file_config().get("additional_parameters") or {}
        rows = config.get("default_rows") or []
        return [dict(row) for row in rows if isinstance(row, Mapping)]

    @property
    def validation(self) -> Mapping[str, Any]:
        config = self._response_file_config().get("validation") or {}
        return config if isinstance(config, Mapping) else {}

    def response_values_with_defaults(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        rendered, _ = self._response_values_with_defaults(values)
        return rendered

    def should_write_response_value(
        self,
        key: str,
        value: Any,
        context: Mapping[str, Any],
    ) -> bool:
        defaults = self.validation.get("defaults") or {}
        if not isinstance(defaults, Mapping):
            return True
        config = defaults.get(str(key))
        if config is None:
            return True
        if not isinstance(config, Mapping):
            config = {"value": config}
        if bool(config.get("write", True)):
            return True
        if not condition_matches(config.get("when"), self._condition_context(context)):
            return True
        if "value" not in config:
            return True
        return not _same_rsp_value(value, config.get("value"))

    def response_validation_errors(self, values: Mapping[str, Any]) -> List[str]:
        _, effective = self._response_values_with_defaults(values)
        context = self._condition_context(effective)
        required_rules = self.validation.get("required") or []
        missing: List[str] = []
        invalid: List[str] = []

        for rule in required_rules:
            if not isinstance(rule, Mapping):
                continue
            if not condition_matches(rule.get("when"), context):
                continue

            if "one_of" in rule:
                options = [str(key) for key in rule.get("one_of") or []]
                if options and not any(_has_value(effective.get(key)) for key in options):
                    missing.append(
                        "one of "
                        + ", ".join(self._field_display(key) for key in options)
                    )
                continue

            key = str(rule.get("key") or "")
            if not key:
                continue
            value = effective.get(key)
            if not _has_value(value):
                missing.append(self._field_display(key))
                continue

            expected = rule.get("expected_value")
            if expected is not None and not _value_matches(value, expected):
                invalid.append(f"{self._field_display(key)} must be {expected}")

        errors: List[str] = []
        if missing:
            errors.append("Missing required response file fields: " + ", ".join(missing))
        if invalid:
            errors.append("Invalid response file field values: " + ", ".join(invalid))
        return errors

    def field_required_hint(
        self,
        key: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Return whether a field needs user input for the active profile context."""
        key_s = str(key)
        _, effective = self._response_values_with_defaults(context or {})
        condition_context = self._condition_context(effective)

        for rule in self.validation.get("required") or []:
            if not isinstance(rule, Mapping):
                continue
            if "one_of" in rule:
                continue
            if str(rule.get("key") or "") != key_s:
                continue
            if not condition_matches(rule.get("when"), condition_context):
                continue
            if _required_rule_satisfied_by_effective_value(key_s, rule, effective):
                return False
            return True

        return False

    def decision_input_response_values(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        controls = self.decision_input_controls
        context = self._decision_input_context(values, controls)
        condition_context = self._condition_context(context)
        out: Dict[str, Any] = {}
        for name, config in controls.items():
            if not isinstance(config, Mapping):
                continue
            selected_value = context.get(str(name))
            response_values = config.get("response_values")
            if isinstance(response_values, Mapping):
                selected_config = response_values.get(normalize_method(selected_value)) or response_values.get(selected_value)
                if isinstance(selected_config, Mapping):
                    out.update({str(key): value for key, value in selected_config.items()})

            response_key = config.get("response_key")
            write_when = config.get("write_when")
            if not response_key or write_when is None:
                continue
            if not condition_matches(write_when, condition_context):
                continue
            value = self._explicit_decision_input_value(values, str(name), str(response_key))
            if value in (None, ""):
                continue
            out[str(response_key)] = value
        return out

    def _decision_input_response_keys(self) -> List[str]:
        controls = self.decision_input_controls
        keys: List[str] = []
        for config in controls.values():
            response_key = config.get("response_key")
            if response_key:
                keys.append(str(response_key))
            response_values = config.get("response_values")
            if isinstance(response_values, Mapping):
                for response_config in response_values.values():
                    if isinstance(response_config, Mapping):
                        keys.extend(str(key) for key in response_config.keys())
        return keys

    def _platform_allowed_mediums(self, context: Mapping[str, Any]) -> Optional[set[str]]:
        platform_mediums = (
            self._response_file_config().get("platform_mediums")
            or {}
        )
        if not platform_mediums:
            return None
        platform = (
            _context_value(context, "PLATFORM_TYPE")
            or _context_value(context, "platform_type")
            or _context_value(context, "platform")
        )
        if not platform:
            return None
        values = platform_mediums.get(normalize_method(platform))
        return {normalize_method(value) for value in values} if values else set()

    def _decision_inputs_config(self) -> Mapping[str, Any]:
        config = self.data.get("decision_inputs") or {}
        return config if isinstance(config, Mapping) else {}

    def _response_file_config(self) -> Mapping[str, Any]:
        config = self.data.get("response_file") or {}
        return config if isinstance(config, Mapping) else {}

    def _response_ui_config(self) -> Mapping[str, Any]:
        config = self._response_file_config().get("ui") or {}
        return config if isinstance(config, Mapping) else {}

    def _job_submission_config(self) -> Mapping[str, Any]:
        config = self.data.get("job_submission") or {}
        return config if isinstance(config, Mapping) else {}

    def _condition_context(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(context)
        for key, value in context.items():
            key_s = str(key)
            result[key_s.upper()] = value
            result[key_s.lower()] = value
        return result

    def _decision_input_context(
        self,
        values: Mapping[str, Any],
        controls: Mapping[str, Any],
    ) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        for name, config in controls.items():
            if not isinstance(config, Mapping):
                continue
            name_s = str(name)
            response_key = str(config.get("response_key") or "")
            value = values.get(response_key) if response_key else None
            if value in (None, ""):
                value = values.get(name_s)
            if value in (None, ""):
                value = config.get("default")
            context[name_s] = value
            if response_key:
                context[response_key] = value
        return context

    def _explicit_decision_input_value(
        self,
        values: Mapping[str, Any],
        control_name: str,
        response_key: str,
    ) -> Any:
        if response_key in values:
            return values.get(response_key)
        return values.get(control_name)

    def _response_values_with_defaults(
        self,
        values: Mapping[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        rendered = dict(values)
        effective = dict(values)
        defaults = self.validation.get("defaults") or {}
        if not isinstance(defaults, Mapping):
            return rendered, effective

        for key, config in defaults.items():
            key_s = str(key)
            if not isinstance(config, Mapping):
                config = {"value": config}
            if not condition_matches(config.get("when"), self._condition_context(effective)):
                continue
            value = config.get("value")
            if value is None:
                continue

            if not _has_value(effective.get(key_s)):
                effective[key_s] = value
            if bool(config.get("write", True)) and not _has_value(rendered.get(key_s)):
                rendered[key_s] = value

        return rendered, effective

    def _field_display(self, key: str) -> str:
        return key


_PROFILE_CACHE: Optional[Dict[str, MigrationProfile]] = None


def normalize_method(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def get_profile(method: Any) -> MigrationProfile:
    normalized = normalize_method(method)
    profiles = load_profiles()
    profile = profiles.get(normalized)
    if profile is None:
        raise ValueError(f"Unsupported migration method: {method or '(blank)'}")
    return profile


def load_profiles() -> Dict[str, MigrationProfile]:
    global _PROFILE_CACHE
    if _PROFILE_CACHE is None:
        profiles: Dict[str, MigrationProfile] = {}
        for path in sorted(PROFILE_DIR.glob("*.yaml")):
            with open(path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            profile = MigrationProfile(data, path)
            if profile.method in profiles:
                raise ValueError(f"Duplicate migration profile method: {profile.method}")
            profiles[profile.method] = profile
        if not profiles:
            raise ValueError(f"No active migration profiles found in {PROFILE_DIR}")
        _PROFILE_CACHE = profiles
    return dict(_PROFILE_CACHE)


def _field_list(value: Any, label: str) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    out = [str(item) for item in value]
    if any(not item.strip() for item in out):
        raise ValueError(f"{label} must not contain blank field names")
    return out


def _validate_known_fields(
    path: Path,
    label: str,
    fields: Iterable[str],
    known_fields: set[str],
) -> None:
    unknown = sorted(str(field) for field in fields if str(field) not in known_fields)
    if unknown:
        raise ValueError(f"{path} {label} references unknown fields: " + ", ".join(unknown))


def _validate_known_sections(
    path: Path,
    label: str,
    sections: Iterable[str],
    known_sections: set[str],
) -> None:
    unknown = sorted(str(section) for section in sections if str(section) not in known_sections)
    if unknown:
        raise ValueError(f"{path} {label} references unknown sections: " + ", ".join(unknown))


def _validate_ui_title(path: Path, item: Mapping[str, Any], label: str) -> None:
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{path} {label}.title must be a non-empty string")


def _layout_section_refs(value: Any, label: str) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    if not value:
        raise ValueError(f"{label} must not be empty")
    refs: List[str] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            if not item.strip():
                raise ValueError(f"{label}[{index}] must not be blank")
            refs.append(item)
            continue
        if isinstance(item, Mapping):
            title = item.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"{label}[{index}].title must be a non-empty string")
            refs.extend(_layout_section_refs(item.get("sections"), f"{label}[{index}].sections"))
            continue
        raise ValueError(f"{label}[{index}] must be a section name or group mapping")
    return refs


def _copy_layout_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    copied: Dict[str, Any] = {"type": str(item.get("type") or "")}
    for key in ("title", "section"):
        if key in item:
            copied[key] = item[key]
    for key in ("tabs", "sections"):
        if key in item:
            copied[key] = _copy_layout_entries(item[key])
    return copied


def _copy_layout_entries(value: Any) -> List[Any]:
    entries: List[Any] = []
    for item in value or []:
        if isinstance(item, Mapping):
            group: Dict[str, Any] = {"title": item.get("title")}
            if "sections" in item:
                group["sections"] = _copy_layout_entries(item.get("sections"))
            entries.append(group)
        else:
            entries.append(str(item))
    return entries


def _validate_section_references(
    path: Path,
    label: str,
    sections: Mapping[str, Any],
    known_fields: set[str],
) -> None:
    _validate_known_fields(path, label, _section_field_refs(sections, f"{path} {label}"), known_fields)


def _section_field_refs(value: Any, label: str) -> List[str]:
    if isinstance(value, Mapping):
        out: List[str] = []
        for name, child in value.items():
            out.extend(_section_field_refs(child, f"{label}.{name}"))
        return out
    if isinstance(value, list):
        return _field_list(value, label)
    raise ValueError(f"{label} must be a mapping or list of field names")


def _flatten_field_groups(value: Any) -> List[str]:
    if isinstance(value, Mapping):
        out: List[str] = []
        for group in value.values():
            out.extend(_flatten_field_groups(group))
        return out
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _nested_section_value(sections: Mapping[str, Any], section: str) -> Any:
    current: Any = sections
    for part in str(section or "").split("."):
        if not part:
            continue
        if not isinstance(current, Mapping):
            return []
        current = current.get(part)
    return current


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _context_value(context: Mapping[str, Any], key: str) -> Any:
    if key in context:
        return context[key]
    lowered = key.lower()
    for existing_key, value in context.items():
        if str(existing_key).lower() == lowered:
            return value
    return None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _value_matches(value: Any, expected: Any) -> bool:
    return normalize_method(value) == normalize_method(expected)


def _same_rsp_value(left: Any, right: Any) -> bool:
    return normalize_rsp_value(left).strip() == normalize_rsp_value(right).strip()


def _required_rule_satisfied_by_effective_value(
    key: str,
    rule: Mapping[str, Any],
    effective: Mapping[str, Any],
) -> bool:
    value = effective.get(key)
    if not _has_value(value):
        return False
    expected = rule.get("expected_value")
    return expected is None or _value_matches(value, expected)
