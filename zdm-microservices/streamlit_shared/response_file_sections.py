from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request
from streamlit_shared.response_file_form import (
    FieldSpec,
    LogicalScenario,
    MIGRATION_TYPE_OPTIONS,
    REMAP_TYPE_OPTIONS,
    SELECT_PROJECT,
    SELECT_WALLET,
    collect_additional_parameters,
    collect_metadata_remaps,
    default_method,
    include_schemas_from_text,
    logical_medium_guidance,
    logical_medium_options,
    logical_scenario_from_project,
    logical_scenario_option_label,
    medium_options,
    method_options,
    normalize_method,
    normalize_logical_scenario,
    project_environment_response_values,
    profile_additional_default_rows,
    profile_medium_field_specs,
    profile_medium_section_field_specs,
    profile_section_field_specs,
    response_method_supported,
    same_method_copy_candidates,
)
from streamlit_shared.response_file_payload import validate_responsefile_copy_response
from streamlit_shared.ui import field_label, param_help


@dataclass(frozen=True)
class ResponseFileSelection:
    migration_type: str
    migration_method: str
    selected_migration_method: str
    logical_scenario: LogicalScenario | None
    platform_type: str
    derived_response_values: Dict[str, Any]
    medium: str
    is_oss: bool
    response_method_supported: bool


@dataclass(frozen=True)
class ResponseFileFormData:
    values: Dict[str, Any]
    remaps: List[List[str]]
    additional: Dict[str, str]


def render_responsefile_project_controls(project: str) -> bool:
    row_p, row_b1, row_b2 = st.columns([6, 1.4, 1.4], vertical_alignment="center")
    with row_p:
        st.markdown(f"### Project: `{project}`")

    if "rf_expand_all" not in st.session_state:
        st.session_state["rf_expand_all"] = False
    with row_b1:
        if st.button("Expand", key="rf_expand_all_btn", width='stretch'):
            st.session_state["rf_expand_all"] = True
    with row_b2:
        if st.button("Collapse", key="rf_collapse_all_btn", width='stretch'):
            st.session_state["rf_expand_all"] = False
    return bool(st.session_state.get("rf_expand_all", False))


def render_responsefile_basics(
    *,
    project: str,
    projects_resp: Any,
    connections_resp: Any,
    api_base: str,
    auth: Any,
) -> ResponseFileSelection:
    st.markdown("#### Basics")
    migration_type = st.selectbox(
        "Migration type",
        MIGRATION_TYPE_OPTIONS,
        key="rf_migration_type",
        help=param_help("MIGRATION_TYPE"),
    )

    method_opts = method_options(migration_type)
    default_method_value = default_method(migration_type)
    if not method_opts:
        st.error(f"No active migration profile is available for {migration_type}.")
        st.stop()
    platform_type = ""
    logical_scenario: LogicalScenario | None = None
    project_record = projects_resp.get(project)
    if not isinstance(project_record, dict):
        st.error(f"GET /projects API contract error: selected project '{project}' is missing.")
        st.stop()

    if migration_type == "Logical":
        logical_scenario = logical_scenario_from_project(
            project_record,
            connections_resp,
            default_method_value,
        )
        _render_logical_scenario_summary(logical_scenario)

    if st.session_state.get("rf_migration_method") not in method_opts:
        st.session_state["rf_migration_method"] = default_method_value

    migration_method = st.selectbox(
        "Migration method",
        method_opts,
        key="rf_migration_method",
        help=param_help("MIGRATION_METHOD"),
    )

    selected_migration_method = normalize_method(migration_method)
    supported = response_method_supported(selected_migration_method)
    if not supported:
        st.error(f"{selected_migration_method} is not supported in this refactor yet.")

    derived_response_values = project_environment_response_values(
        project_record,
        connections_resp,
        selected_migration_method,
    )
    platform_type = str(derived_response_values.get("PLATFORM_TYPE") or "")

    if logical_scenario is not None:
        logical_scenario = normalize_logical_scenario(
            LogicalScenario(
                migration_method=selected_migration_method,
                source_type=logical_scenario.source_type,
                target_type=logical_scenario.target_type,
            )
        )

    _render_copy_values(project, projects_resp, selected_migration_method, api_base, auth)

    medium_opts = medium_options(
        migration_type,
        selected_migration_method,
        platform_type,
        logical_scenario=logical_scenario,
    )
    medium_labels = (
        {option.value: option.label for option in logical_medium_options(logical_scenario)}
        if migration_type == "Logical"
        else {}
    )
    if st.session_state.get("rf_medium") not in medium_opts:
        st.session_state["rf_medium"] = medium_opts[0]

    medium = st.selectbox(
        "Data transfer medium",
        medium_opts,
        key="rf_medium",
        help=param_help("DATA_TRANSFER_MEDIUM"),
        format_func=lambda value: medium_labels.get(value, value),
    )
    if migration_type == "Logical":
        _render_logical_medium_notes(logical_scenario, medium)

    return ResponseFileSelection(
        migration_type=migration_type,
        migration_method=migration_method,
        selected_migration_method=selected_migration_method,
        logical_scenario=logical_scenario,
        platform_type=platform_type,
        derived_response_values=derived_response_values,
        medium=medium,
        is_oss=normalize_method(medium) == "OSS",
        response_method_supported=supported,
    )


def _render_logical_scenario_summary(logical_scenario: LogicalScenario) -> None:
    st.caption(
        "Scenario: "
        + logical_scenario_option_label("source_type", logical_scenario.source_type)
        + " to "
        + logical_scenario_option_label("target_type", logical_scenario.target_type)
    )


def _render_logical_medium_notes(
    logical_scenario: LogicalScenario | None,
    selected_medium: str,
) -> None:
    guidance = logical_medium_guidance(selected_medium)
    if guidance:
        st.caption(guidance)

    disabled_options = [
        option
        for option in logical_medium_options(logical_scenario)
        if not option.enabled and option.disabled_reason
    ]
    if disabled_options:
        with st.expander("Unavailable media"):
            for option in disabled_options:
                st.caption(f"{option.label}: {option.disabled_reason}")


def render_responsefile_form_sections(
    *,
    selection: ResponseFileSelection,
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
) -> ResponseFileFormData:
    values: Dict[str, Any] = {}
    if selection.platform_type:
        values["PLATFORM_TYPE"] = selection.platform_type
    values.update(selection.derived_response_values)
    if selection.logical_scenario:
        values["source_type"] = selection.logical_scenario.source_type
        values["target_type"] = selection.logical_scenario.target_type

    st.divider()
    values.update(_render_source_target_section(selection, wallet_names, wallet_map, expand_all))

    st.divider()
    values.update(_render_transfer_settings_section(selection, expand_all))
    values.update(_render_oci_authentication_section(selection, expand_all))

    data_pump_values, remaps, additional = _render_data_pump_sections(selection, expand_all)
    values.update(data_pump_values)
    values = preserve_derived_response_values(values, selection.derived_response_values)

    return ResponseFileFormData(values=values, remaps=remaps, additional=additional)


def _render_copy_values(
    project: str,
    projects_resp: Any,
    selected_migration_method: str,
    api_base: str,
    auth: Any,
) -> None:
    copy_candidates = same_method_copy_candidates(projects_resp, project, selected_migration_method)
    if not copy_candidates:
        st.caption("No same-method source projects available.")
        return

    copy_source_options = [SELECT_PROJECT] + copy_candidates
    if st.session_state.get("rf_copy_source_project") not in copy_source_options:
        st.session_state["rf_copy_source_project"] = copy_source_options[0]

    copy_col_source, copy_col_action = st.columns([3, 1], vertical_alignment="bottom")
    with copy_col_source:
        copy_source_project = st.selectbox(
            "Copy values from project",
            copy_source_options,
            key="rf_copy_source_project",
        )
    with copy_col_action:
        copy_clicked = st.button(
            "Copy values",
            key="rf_copy_values_btn",
            disabled=copy_source_project == SELECT_PROJECT,
            width='stretch',
        )

    if not copy_clicked:
        return

    copy_resp = api_request(
        "post",
        "/responsefiles/copy",
        api_base,
        auth,
        payload={
            "source_project": copy_source_project,
            "target_project": project,
            "migration_method": selected_migration_method,
        },
    )
    if copy_resp is not None:
        try:
            validate_responsefile_copy_response(
                copy_resp,
                expected_source_project=copy_source_project,
                expected_target_project=project,
                expected_method=selected_migration_method,
            )
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        st.session_state.pop("rf_remap_table", None)
        st.session_state.pop("rf_additional_table", None)
        st.session_state["rf_form_loaded_project"] = ""
        st.rerun()


def _render_source_target_section(
    selection: ResponseFileSelection,
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
) -> Dict[str, Any]:
    values: Dict[str, Any] = {}

    with st.expander("Source & Target ", expanded=expand_all):
        if selection.migration_type == "Logical":
            source_specs = _section_specs(selection, "source_database")
            target_specs = _section_specs(selection, "target_database")
            tab_src, tab_tgt = st.tabs(["Source database", "Target database"])
            with tab_src:
                values.update(
                    _render_fields(
                        editable_field_specs(
                            source_specs,
                            selection.derived_response_values,
                        ),
                        wallet_names,
                        wallet_map,
                    )
                )
                _render_derived_fields(
                    source_specs,
                    selection.derived_response_values,
                )

            with tab_tgt:
                values.update(
                    _render_fields(
                        editable_field_specs(
                            target_specs,
                            selection.derived_response_values,
                        ),
                        wallet_names,
                        wallet_map,
                    )
                )
                _render_derived_fields(
                    target_specs,
                    selection.derived_response_values,
                )

        else:
            st.caption("This migration type is not active in the response-file profile catalog.")

    return values


def _render_transfer_settings_section(
    selection: ResponseFileSelection,
    expand_all: bool,
) -> Dict[str, Any]:
    values: Dict[str, Any] = {}

    with st.expander("Transfer settings", expanded=expand_all):
        if selection.is_oss and selection.migration_type == "Logical":
            st.markdown("**Object Storage (Logical)**")
            values.update(_render_fields(_medium_section_specs(selection, "transfer_settings")))
        elif selection.migration_type == "Logical":
            medium_specs = _medium_specs(selection)
            if medium_specs:
                st.markdown(f"**{selection.medium} transfer**")
                values.update(_render_fields(medium_specs))
            else:
                st.caption("No automated transfer fields for current logical medium.")
        else:
            st.caption("No Object Storage fields for current selection.")

    return values


def _render_oci_authentication_section(
    selection: ResponseFileSelection,
    expand_all: bool,
) -> Dict[str, Any]:
    if not (selection.is_oss and selection.migration_type == "Logical"):
        return {}

    with st.expander("OCI authentication", expanded=expand_all):
        return _render_fields(_medium_section_specs(selection, "oci_authentication"))


def _render_data_pump_sections(
    selection: ResponseFileSelection,
    expand_all: bool,
) -> tuple[Dict[str, Any], List[List[str]], Dict[str, str]]:
    values: Dict[str, Any] = {"include_schemas": []}

    remap_rows = pd.DataFrame()
    additional_default_rows = (
        profile_additional_default_rows(selection.selected_migration_method)
        or [{"key": "", "value": ""}]
    )
    additional_rows = pd.DataFrame(additional_default_rows)

    if selection.migration_type != "Logical":
        return values, [], {}

    st.divider()
    with st.expander("Data Pump", expanded=expand_all):
        values.update(_render_fields(_section_specs(selection, "data_pump")))

        with st.expander("Tablespace remap", expanded=expand_all):
            values.update(_render_fields(_section_specs(selection, "tablespace")))
            st.caption("Metadata remaps (`DATAPUMPSETTINGS_METADATAREMAPS`)")
            remap_rows = st.data_editor(
                _prefill_dataframe(
                    "rf_remap_prefill",
                    [{"type": "REMAP_TABLESPACE", "oldValue": "", "newValue": ""}],
                ),
                num_rows="dynamic",
                column_config={
                    "type": st.column_config.SelectboxColumn("Type", options=REMAP_TYPE_OPTIONS, required=True),
                    "oldValue": st.column_config.TextColumn("Old value", required=True),
                    "newValue": st.column_config.TextColumn("New value", required=True),
                },
                key="rf_remap_table",
            )

        with st.expander("Schemas", expanded=expand_all):
            include_schemas_raw = st.text_area(
                field_label("Schemas to include (one per line)", True),
                height=140,
                key="rf_include_schemas",
                help=param_help("include_schemas"),
            )
            values["include_schemas"] = include_schemas_from_text(
                include_schemas_raw,
                selection.migration_type,
            )
            st.caption(f"Count: {len(values['include_schemas'])}")

    st.divider()
    with st.expander("Additional parameters (key/value)", expanded=expand_all):
        additional_rows = st.data_editor(
            _prefill_dataframe("rf_additional_prefill", additional_default_rows),
            num_rows="dynamic",
            column_config={
                "key": st.column_config.TextColumn("Key", required=False),
                "value": st.column_config.TextColumn("Value", required=False),
            },
            key="rf_additional_table",
        )

    return (
        values,
        collect_metadata_remaps(remap_rows, selection.migration_type),
        collect_additional_parameters(additional_rows),
    )


def _section_specs(selection: ResponseFileSelection, section: str) -> tuple[FieldSpec, ...]:
    return profile_section_field_specs(selection.selected_migration_method, section)


def _medium_specs(selection: ResponseFileSelection) -> tuple[FieldSpec, ...]:
    return profile_medium_field_specs(selection.selected_migration_method, selection.medium)


def _medium_section_specs(selection: ResponseFileSelection, section: str) -> tuple[FieldSpec, ...]:
    return profile_medium_section_field_specs(
        selection.selected_migration_method,
        selection.medium,
        section,
    )


def _prefill_dataframe(state_key: str, default_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    prefill = st.session_state.pop(state_key, None)
    if prefill is None:
        return pd.DataFrame(default_rows)
    if isinstance(prefill, pd.DataFrame):
        return prefill
    return pd.DataFrame(prefill)


def _render_fields(
    specs: tuple[FieldSpec, ...],
    wallet_names: List[str] | None = None,
    wallet_map: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    return {
        spec.key: _render_field(spec, wallet_names or [SELECT_WALLET], wallet_map or {})
        for spec in specs
    }


def editable_field_specs(
    specs: tuple[FieldSpec, ...],
    derived_response_values: Mapping[str, Any],
) -> tuple[FieldSpec, ...]:
    return tuple(
        spec
        for spec in specs
        if spec.key not in derived_response_values
    )


def preserve_derived_response_values(
    values: Mapping[str, Any],
    derived_response_values: Mapping[str, Any],
) -> Dict[str, Any]:
    merged = dict(values)
    for key, value in derived_response_values.items():
        if value not in (None, ""):
            merged[str(key)] = value
    return merged


def _render_derived_fields(
    specs: tuple[FieldSpec, ...],
    derived_response_values: Mapping[str, Any],
) -> None:
    for spec in specs:
        value = derived_response_values.get(spec.key)
        if value in (None, ""):
            continue
        st.caption(f"{spec.label}: `{value}` (from project connection)")


def _render_field(
    spec: FieldSpec,
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
) -> Any:
    help_key = spec.help_key or spec.key
    label = field_label(spec.label, spec.required)
    help_text = param_help(help_key)

    if spec.control == "select":
        options = list(spec.options)
        index = options.index(spec.default) if spec.default in options else 0
        return st.selectbox(label, options, index=index, key=spec.state_key, help=help_text)

    if spec.control == "number":
        kwargs: Dict[str, Any] = {
            "label": label,
            "key": spec.state_key,
            "help": help_text,
        }
        if spec.min_value is not None:
            kwargs["min_value"] = spec.min_value
        if spec.max_value is not None:
            kwargs["max_value"] = spec.max_value
        if spec.step is not None:
            kwargs["step"] = spec.step
        if spec.state_key not in st.session_state:
            kwargs["value"] = spec.default
        return st.number_input(**kwargs)

    if spec.control == "wallet":
        selected_wallet = st.selectbox(label, wallet_names, key=spec.state_key, help=help_text)
        return wallet_map.get(selected_wallet, "") if selected_wallet != SELECT_WALLET else ""

    kwargs = {"key": spec.state_key, "help": help_text}
    if spec.default not in ("", None):
        kwargs["value"] = spec.default
    return st.text_input(label, **kwargs)
