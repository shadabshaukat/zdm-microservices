from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, validate_payload_or_stop
from streamlit_shared.response_file_form import (
    FieldSpec,
    REMAP_TYPE_OPTIONS,
    SELECT_PROJECT,
    SELECT_WALLET,
    collect_additional_parameters,
    collect_metadata_remaps,
    include_schemas_from_text,
    migration_medium_guidance,
    migration_medium_options,
    migration_decision_input_summary_parts,
    migration_decision_input_values_from_project,
    migration_method_label,
    migration_type_for_method,
    normalize_method,
    project_environment_response_values,
    profile_additional_default_rows,
    profile_medium_fields_title,
    profile_medium_section_field_specs,
    profile_medium_section_names,
    profile_medium_unsectioned_field_specs,
    profile_response_layout,
    profile_section_field_specs,
    profile_section_label,
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
    decision_input_values: Dict[str, Any]
    platform_type: str
    derived_response_values: Dict[str, Any]
    medium: str
    response_method_supported: bool


@dataclass(frozen=True)
class ResponseFileFormData:
    values: Dict[str, Any]
    remaps: List[List[str]]
    additional: Dict[str, str]


@dataclass(frozen=True)
class RenderedFields:
    values: Dict[str, Any]
    remaps: List[List[str]]


def responsefile_unavailable_message(selected_migration_method: str) -> str:
    method_label = migration_method_label(selected_migration_method)
    return f"ZEUS currently supports Logical Offline response files only. This project uses {method_label}."


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
    project_record = projects_resp.get(project)
    if not isinstance(project_record, dict):
        st.error(f"Selected project '{project}' is no longer available. Refresh the page and choose a project again.")
        st.stop()

    selected_migration_method = normalize_method(project_record.get("migration_method"))
    if not selected_migration_method:
        st.error("This project is missing a migration method. Create the project again before building response files.")
        st.stop()
    try:
        migration_type = migration_type_for_method(selected_migration_method)
    except Exception as exc:
        st.error(f"This project's migration method is not available for response-file generation: {exc}")
        st.stop()
    migration_method = selected_migration_method
    st.session_state["rf_migration_method"] = selected_migration_method
    st.markdown(
        " ".join(
            [
                f"`Migration method: {migration_method_label(selected_migration_method)}`",
                f"`Profile: {selected_migration_method}`",
            ]
        )
    )
    supported = response_method_supported(selected_migration_method)
    if not supported:
        st.error(responsefile_unavailable_message(selected_migration_method))

    decision_input_values = migration_decision_input_values_from_project(
        selected_migration_method,
        project_record,
        connections_resp,
    )
    _render_decision_input_summary(selected_migration_method, decision_input_values)

    derived_response_values = project_environment_response_values(
        project_record,
        connections_resp,
        selected_migration_method,
    )
    platform_type = str(derived_response_values.get("PLATFORM_TYPE") or "")

    _render_copy_values(project, projects_resp, selected_migration_method, api_base, auth)

    medium_context = {**decision_input_values, **derived_response_values}
    if platform_type:
        medium_context["PLATFORM_TYPE"] = platform_type
    medium_option_rows = migration_medium_options(
        selected_migration_method,
        medium_context,
    )
    medium_opts = [option.value for option in medium_option_rows if option.enabled]
    medium_labels = {option.value: option.label for option in medium_option_rows}
    if not medium_opts:
        st.error("No data transfer media are available for this project and migration method.")
        st.stop()
    if st.session_state.get("rf_medium") not in medium_opts:
        st.session_state["rf_medium"] = medium_opts[0]

    medium = st.selectbox(
        "Data transfer medium",
        medium_opts,
        key="rf_medium",
        help=param_help("DATA_TRANSFER_MEDIUM"),
        format_func=lambda value: medium_labels.get(value, value),
    )
    _render_medium_notes(selected_migration_method, medium, medium_option_rows)

    return ResponseFileSelection(
        migration_type=migration_type,
        migration_method=migration_method,
        selected_migration_method=selected_migration_method,
        decision_input_values=decision_input_values,
        platform_type=platform_type,
        derived_response_values=derived_response_values,
        medium=medium,
        response_method_supported=supported,
    )


def _render_decision_input_summary(migration_method: str, decision_input_values: Mapping[str, Any]) -> None:
    parts = migration_decision_input_summary_parts(migration_method, decision_input_values)
    if not parts:
        return
    separator = " to " if len(parts) == 2 else " / "
    st.caption("Migration path: " + separator.join(parts))


def _render_medium_notes(
    migration_method: str,
    selected_medium: str,
    medium_option_rows: List[Any],
) -> None:
    guidance = migration_medium_guidance(migration_method, selected_medium)
    if guidance:
        st.caption(guidance)

    disabled_options = [
        option
        for option in medium_option_rows
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
    remaps: List[List[str]] = []
    additional: Dict[str, str] = {}
    if selection.platform_type:
        values["PLATFORM_TYPE"] = selection.platform_type
    values.update(selection.derived_response_values)
    values.update(selection.decision_input_values)

    for item in profile_response_layout(selection.selected_migration_method):
        st.divider()
        item_type = str(item.get("type") or "")
        if item_type == "additional_parameters":
            additional = _render_additional_parameters(selection, item, expand_all)
            continue
        rendered = _render_layout_item(selection, item, wallet_names, wallet_map, expand_all)
        values.update(rendered.values)
        remaps.extend(rendered.remaps)

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
        validate_payload_or_stop(
            copy_resp,
            validate_responsefile_copy_response,
            expected_source_project=copy_source_project,
            expected_target_project=project,
            expected_method=selected_migration_method,
        )
        st.session_state.pop("rf_remap_table", None)
        st.session_state.pop("rf_additional_table", None)
        st.session_state["rf_form_loaded_project"] = ""
        st.rerun()


def _render_layout_item(
    selection: ResponseFileSelection,
    item: Mapping[str, Any],
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
) -> RenderedFields:
    item_type = str(item.get("type") or "")
    if item_type == "tabs":
        return _render_tab_layout(selection, item, wallet_names, wallet_map, expand_all)
    if item_type == "medium":
        return _render_medium_layout(selection, wallet_names, wallet_map, expand_all)
    if item_type == "sections":
        return _render_sections_layout(selection, item, wallet_names, wallet_map, expand_all)
    if item_type == "section":
        section = str(item.get("section") or "")
        title = str(item.get("title") or _section_label(selection, section))
        with st.expander(title, expanded=expand_all):
            return _render_section(selection, section, wallet_names, wallet_map)
    raise ValueError(f"Unsupported response-file layout item type: {item_type}")


def _render_tab_layout(
    selection: ResponseFileSelection,
    item: Mapping[str, Any],
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
) -> RenderedFields:
    values: Dict[str, Any] = {}
    remaps: List[List[str]] = []
    tab_sections = [str(section) for section in item.get("tabs") or []]
    with st.expander(str(item.get("title") or ""), expanded=expand_all):
        tabs = st.tabs([_section_label(selection, section) for section in tab_sections])
        for tab, section in zip(tabs, tab_sections):
            with tab:
                rendered = _render_section(selection, section, wallet_names, wallet_map)
                values.update(rendered.values)
                remaps.extend(rendered.remaps)
    return RenderedFields(values=values, remaps=remaps)


def _render_sections_layout(
    selection: ResponseFileSelection,
    item: Mapping[str, Any],
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
) -> RenderedFields:
    with st.expander(str(item.get("title") or ""), expanded=expand_all):
        return _render_section_entries(
            selection,
            item.get("sections") or [],
            wallet_names,
            wallet_map,
            expand_all,
            first_inline=True,
        )


def _render_section_entries(
    selection: ResponseFileSelection,
    entries: Any,
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
    *,
    first_inline: bool = False,
) -> RenderedFields:
    values: Dict[str, Any] = {}
    remaps: List[List[str]] = []
    for index, entry in enumerate(entries or []):
        if not _layout_entry_has_visible_fields(selection, entry):
            continue
        if isinstance(entry, str):
            if first_inline and index == 0:
                rendered = _render_section(selection, entry, wallet_names, wallet_map)
            else:
                with st.expander(_section_label(selection, entry), expanded=expand_all):
                    rendered = _render_section(selection, entry, wallet_names, wallet_map)
        elif isinstance(entry, Mapping):
            with st.expander(str(entry.get("title") or ""), expanded=expand_all):
                rendered = _render_section_entries(
                    selection,
                    entry.get("sections") or [],
                    wallet_names,
                    wallet_map,
                    expand_all,
                    first_inline=True,
                )
        else:
            raise ValueError(f"Unsupported response-file layout entry: {entry!r}")
        values.update(rendered.values)
        remaps.extend(rendered.remaps)
    return RenderedFields(values=values, remaps=remaps)


def _layout_entry_has_visible_fields(selection: ResponseFileSelection, entry: Any) -> bool:
    if isinstance(entry, str):
        return bool(_section_specs(selection, entry))
    if isinstance(entry, Mapping):
        return any(
            _layout_entry_has_visible_fields(selection, child)
            for child in entry.get("sections") or []
        )
    return True


def _render_medium_layout(
    selection: ResponseFileSelection,
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
    expand_all: bool,
) -> RenderedFields:
    values: Dict[str, Any] = {}
    remaps: List[List[str]] = []
    section_names = profile_medium_section_names(
        selection.selected_migration_method,
        selection.medium,
    )

    for section in section_names:
        with st.expander(_section_label(selection, section), expanded=expand_all):
            rendered = _render_fields(
                _medium_section_specs(selection, section),
                selection,
                wallet_names,
                wallet_map,
            )
            values.update(rendered.values)
            remaps.extend(rendered.remaps)

    unsectioned_specs = _medium_unsectioned_specs(selection)
    if unsectioned_specs:
        with st.expander(
            profile_medium_fields_title(selection.selected_migration_method),
            expanded=expand_all,
        ):
            st.markdown(f"**{selection.medium} transfer**")
            rendered = _render_fields(unsectioned_specs, selection, wallet_names, wallet_map)
            values.update(rendered.values)
            remaps.extend(rendered.remaps)
    elif not section_names:
        with st.expander(
            profile_medium_fields_title(selection.selected_migration_method),
            expanded=expand_all,
        ):
            st.caption("No response-file fields are required for this transfer medium.")

    return RenderedFields(values=values, remaps=remaps)


def _render_section(
    selection: ResponseFileSelection,
    section: str,
    wallet_names: List[str],
    wallet_map: Mapping[str, str],
) -> RenderedFields:
    specs = _section_specs(selection, section)
    rendered = _render_fields(
        editable_field_specs(specs, selection.derived_response_values),
        selection,
        wallet_names,
        wallet_map,
    )
    _render_derived_fields(specs, selection.derived_response_values)
    return rendered


def _render_additional_parameters(
    selection: ResponseFileSelection,
    item: Mapping[str, Any],
    expand_all: bool,
) -> Dict[str, str]:
    additional_default_rows = (
        profile_additional_default_rows(selection.selected_migration_method)
        or [{"key": "", "value": ""}]
    )
    with st.expander(str(item.get("title") or ""), expanded=expand_all):
        additional_rows = st.data_editor(
            _prefill_dataframe("rf_additional_prefill", additional_default_rows),
            num_rows="dynamic",
            column_config={
                "key": st.column_config.TextColumn("Key", required=False),
                "value": st.column_config.TextColumn("Value", required=False),
            },
            key="rf_additional_table",
        )
    return collect_additional_parameters(additional_rows)


def _section_specs(selection: ResponseFileSelection, section: str) -> tuple[FieldSpec, ...]:
    return profile_section_field_specs(
        selection.selected_migration_method,
        section,
        _field_context(selection),
    )


def _medium_unsectioned_specs(selection: ResponseFileSelection) -> tuple[FieldSpec, ...]:
    return profile_medium_unsectioned_field_specs(
        selection.selected_migration_method,
        selection.medium,
        _field_context(selection),
    )


def _medium_section_specs(selection: ResponseFileSelection, section: str) -> tuple[FieldSpec, ...]:
    return profile_medium_section_field_specs(
        selection.selected_migration_method,
        selection.medium,
        section,
        _field_context(selection),
    )


def _section_label(selection: ResponseFileSelection, section: str) -> str:
    return profile_section_label(selection.selected_migration_method, section)


def _field_context(selection: ResponseFileSelection) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        **selection.decision_input_values,
        **selection.derived_response_values,
        "MIGRATION_METHOD": selection.selected_migration_method,
        "DATA_TRANSFER_MEDIUM": selection.medium,
    }
    if selection.platform_type:
        context["PLATFORM_TYPE"] = selection.platform_type
    return context


def _prefill_dataframe(state_key: str, default_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    prefill = st.session_state.pop(state_key, None)
    if prefill is None:
        return pd.DataFrame(default_rows)
    if isinstance(prefill, pd.DataFrame):
        return prefill
    return pd.DataFrame(prefill)


def _render_fields(
    specs: tuple[FieldSpec, ...],
    selection: ResponseFileSelection,
    wallet_names: List[str] | None = None,
    wallet_map: Mapping[str, str] | None = None,
) -> RenderedFields:
    values: Dict[str, Any] = {}
    remaps: List[List[str]] = []
    for spec in specs:
        if spec.control == "metadata_remaps":
            remaps.extend(_render_metadata_remaps_field(spec, selection))
            continue
        if spec.control == "include_schemas":
            values["include_schemas"] = _render_include_schemas_field(spec, selection)
            continue
        values[spec.key] = _render_field(spec, wallet_names or [SELECT_WALLET], wallet_map or {})
    return RenderedFields(values=values, remaps=remaps)


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


def _render_metadata_remaps_field(
    spec: FieldSpec,
    selection: ResponseFileSelection,
) -> List[List[str]]:
    st.caption(f"{spec.label} (`{spec.key}`)")
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
        key=spec.state_key,
    )
    return collect_metadata_remaps(remap_rows)


def _render_include_schemas_field(
    spec: FieldSpec,
    selection: ResponseFileSelection,
) -> List[str]:
    include_schemas_raw = st.text_area(
        field_label(f"{spec.label} (one per line)", spec.required),
        height=140,
        key=spec.state_key,
        help=param_help(spec.help_key or spec.key),
    )
    include_schemas = include_schemas_from_text(include_schemas_raw)
    st.caption(f"Count: {len(include_schemas)}")
    return include_schemas


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
