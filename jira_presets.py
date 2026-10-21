"""Permalink (Begrenzen), Presets und Zufalls-Seed-Button (Standardmuster aus dem Demo-Portfolio, hier mit Auswahl- und Schalter-Reglern)."""

import random
from dataclasses import dataclass

import streamlit as st

import jira_constants as C


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: type
    default: object
    lo: float | None = None
    hi: float | None = None
    options: tuple | None = None        # erlaubte Werte eines Auswahlreglers
    permalink: bool = True              # in der Adresszeile spiegeln?
    szenario: bool = True               # zählt für die Hervorhebung des aktiven Presets (Datenwahl und Ansicht zählen nicht)
    url_skip: tuple = ()                # Werte, die nicht in die Adresszeile gehören (Eigene Gewichte lassen sich nicht teilen)


SETTING_SPECS = {
    "n_epics": SettingSpec("epics", int, C.DEFAULT_N_EPICS, C.N_EPICS_MIN, C.N_EPICS_MAX, szenario=False),
    "seed_input": SettingSpec("seed", int, C.DEFAULT_SEED, 0, C.SEED_MAX, szenario=False),
    "scheme": SettingSpec("schema", str, C.DEFAULT_SCHEME, options=C.SCHEMES, url_skip=(C.SCHEME_CUSTOM,)),
    "weight_mode": SettingSpec("gewicht", str, C.DEFAULT_WEIGHT_MODE, options=C.WEIGHT_MODES),
    "unest_rule": SettingSpec("ungeschaetzt", str, C.DEFAULT_UNEST, options=C.UNEST_RULES),
    "count_level": SettingSpec("zaehlebene", str, C.DEFAULT_LEVEL, options=C.COUNT_LEVELS),
    "blend": SettingSpec("subtasks", bool, False),
    "dimension": SettingSpec("ebene", str, C.DEFAULT_DIM, options=C.DIMENSIONS, szenario=False),
    "dimension2": SettingSpec("ebene2", str, C.DEFAULT_DIM2, options=C.DIMENSIONS_2, szenario=False),
}
PRESET_KEYS = {k: k for k in ("scheme", "weight_mode", "unest_rule", "count_level", "blend")}


def _cast(spec: SettingSpec, raw):
    if spec.caster is bool:
        return str(raw).strip().lower() in ("1", "true", "ja")
    return spec.caster(raw)


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def load_permalink_settings():
    """Einmal je Sitzung: Werte aus der Adresszeile übernehmen, auf die Reglergrenzen begrenzt bzw. auf erlaubte Auswahlwerte geprüft."""
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    for state_key, spec in SETTING_SPECS.items():
        if not spec.permalink or spec.url_param not in qp:
            continue
        try:
            value = _cast(spec, qp[spec.url_param])
        except (ValueError, TypeError):
            continue
        if spec.options is not None and (value not in spec.options or value in spec.url_skip):
            continue
        if spec.lo is not None:
            value = max(spec.lo, value)
        if spec.hi is not None:
            value = min(spec.hi, value)
        st.session_state[state_key] = value
    st.session_state["permalink_loaded"] = True


def sync_query_params(values):
    """`values`: {state_key: aktueller Wert}; die Adresszeile spiegelt die Konfiguration (ohne Datenquelle und ohne Werte aus `url_skip`)."""
    try:
        for state_key, value in values.items():
            spec = SETTING_SPECS[state_key]
            if spec.permalink and value not in spec.url_skip:
                st.query_params[spec.url_param] = str(value)
    except Exception:
        pass


def apply_preset(name):
    for key, state_key in PRESET_KEYS.items():
        if key in C.PRESETS[name]:
            st.session_state[state_key] = C.PRESETS[name][key]


def aktives_preset():
    """Name des Presets, dessen Werte GENAU den aktuellen Einstellungen entsprechen, sonst None.

    Zustandslos: verglichen wird jeder Szenario-Regler aus SETTING_SPECS (ein Preset ohne Eintrag für einen Regler meint dessen Standardwert) mit dem
    Session State. Datenwahl, Beispielgröße und Ansicht (Ebene) gehören nicht zum Szenario. Ein später ergänzter Regler braucht nur seinen Eintrag in
    SETTING_SPECS, dann hebt auch seine Änderung die Markierung auf (tests/test_layout.py prüft das für jeden Regler)."""
    preset_key_of = {state_key: key for key, state_key in PRESET_KEYS.items()}
    for name, preset in C.PRESETS.items():
        if all(
            st.session_state.get(state_key, spec.default) == preset.get(preset_key_of.get(state_key), spec.default)
            for state_key, spec in SETTING_SPECS.items() if spec.szenario
        ):
            return name
    return None


def sidebar_presets():
    """Schnellstart oben in der Seitenleiste; das aktive Preset ist hervorgehoben (`type="primary"`)."""
    if not C.PRESETS:
        return
    st.header("🎯 Schnellstart")
    st.caption("Eine Annahmen-Kombination laden:")
    aktiv = aktives_preset()
    for name in C.PRESETS:
        st.button(
            name, width="stretch", on_click=apply_preset, args=(name,), help=C.PRESET_HELP.get(name, ""), key=f"preset_{name}",
            type="primary" if aktiv == name else "secondary",
        )


def randomize_seed():
    st.session_state["seed_input"] = random.randint(0, C.SEED_MAX)
