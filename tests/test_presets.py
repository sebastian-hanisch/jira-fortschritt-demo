"""Presets: Vollständigkeit, gültige Werte, Standard-Preset = Standardeinstellungen; Permalink begrenzt und prüft Auswahlwerte."""

import jira_constants as C
import jira_evaluation as ev
import jira_presets as P


def test_every_preset_has_help_and_all_keys():
    assert set(C.PRESETS) == set(C.PRESET_HELP)
    for name, preset in C.PRESETS.items():
        assert set(preset) == set(P.PRESET_KEYS), name
        assert C.PRESET_HELP[name]


def test_preset_values_are_valid_options():
    for name, preset in C.PRESETS.items():
        for key, value in preset.items():
            spec = P.SETTING_SPECS[key]
            assert spec.options is None or value in spec.options, (name, key)
        assert preset["scheme"] != C.SCHEME_CUSTOM, name                  # „Eigene Gewichte“ ist kein Szenario, das sich laden lässt


def test_default_preset_equals_the_default_settings():
    first = next(iter(C.PRESETS))
    keys = {"scheme", "weight_mode", "unest_rule", "count_level", "blend"}
    assert ev.Settings(**{k: v for k, v in C.PRESETS[first].items() if k in keys}) == ev.Settings()


def test_presets_differ_pairwise():
    values = [tuple(sorted(p.items())) for p in C.PRESETS.values()]
    assert len(set(values)) == len(values)


def test_setting_specs_cover_every_preset_key_and_every_default_is_valid():
    assert set(P.PRESET_KEYS.values()) <= set(P.SETTING_SPECS)
    for key, spec in P.SETTING_SPECS.items():
        assert spec.options is None or spec.default in spec.options, key
        if spec.lo is not None:
            assert spec.lo <= spec.default <= spec.hi, key


def test_view_and_data_settings_do_not_count_for_the_preset_highlight():
    non_scenario = {k for k, s in P.SETTING_SPECS.items() if not s.szenario}
    assert non_scenario == {"source", "n_epics", "seed_input", "dimension", "dimension2"}
    assert not P.SETTING_SPECS["source"].permalink


def test_custom_scheme_is_never_written_to_the_address_bar():
    assert C.SCHEME_CUSTOM in P.SETTING_SPECS["scheme"].url_skip
