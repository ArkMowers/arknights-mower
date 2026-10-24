from xml.etree import ElementTree as ET

import pytest

from arknights_mower.utils.device.system_ui import (
    system_ui_error_close_point,
    wallpaper_color_state,
)


def dialog_xml(*, anr=True):
    root = ET.Element("hierarchy", rotation="1")
    dialog = ET.SubElement(
        root,
        "node",
        {
            "package": "android",
            "class": "android.widget.FrameLayout",
            "bounds": "[460,417][1459,705]",
        },
    )
    container = ET.SubElement(
        dialog,
        "node",
        {
            "package": "android",
            "class": "android.widget.LinearLayout",
            "bounds": "[480,437][1439,685]",
        },
    )
    controls = {}
    for name, kind, bounds in (
        ("alertTitle", "TextView", "[500,450][1400,500]"),
        ("aerr_close", "Button", "[500,530][1418,600]"),
        ("aerr_wait" if anr else "aerr_restart", "Button", "[500,615][1418,675]"),
    ):
        controls[name] = ET.SubElement(
            container,
            "node",
            {
                "package": "android",
                "resource-id": f"android:id/{name}",
                "class": f"android.widget.{kind}",
                "bounds": bounds,
                "clickable": "true" if kind == "Button" else "false",
                "enabled": "true",
                "text": "任意语言",
            },
        )
    return root, dialog, container, controls


@pytest.mark.parametrize("anr", [False, True])
@pytest.mark.parametrize("as_bytes", [False, True])
def test_close_point_uses_confirmed_control_bounds(anr, as_bytes):
    root, _, _, _ = dialog_xml(anr=anr)
    data = ET.tostring(root, encoding="utf-8" if as_bytes else "unicode")

    assert system_ui_error_close_point(data, anr=anr) == (959, 565)


@pytest.mark.parametrize("anr", [False, True])
def test_complete_disabled_close_control_waits(anr):
    root, _, _, controls = dialog_xml(anr=anr)
    controls["aerr_close"].set("enabled", "false")
    if anr:
        controls["aerr_wait"].set("enabled", "false")

    assert system_ui_error_close_point(ET.tostring(root), anr=anr) is None


@pytest.mark.parametrize("name", ["alertTitle", "aerr_close", "aerr_wait"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_required_controls_are_present_exactly_once(name, duplicate):
    root, _, container, controls = dialog_xml()
    if duplicate:
        container.append(ET.fromstring(ET.tostring(controls[name])))
    else:
        container.remove(controls[name])

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize(
    "location", ["dialog", "container", "alertTitle", "aerr_close", "aerr_wait"]
)
def test_dialog_controls_have_android_package(location):
    root, dialog, container, controls = dialog_xml()
    target = {"dialog": dialog, "container": container, **controls}[location]
    target.set("package", "other.package")

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize("name", ["alertTitle", "aerr_close", "aerr_wait"])
def test_required_control_classes_match_android_dialog(name):
    root, _, _, controls = dialog_xml()
    controls[name].set("class", "android.view.View")

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize("name", ["aerr_close", "aerr_wait"])
def test_action_controls_must_be_clickable(name):
    root, _, _, controls = dialog_xml()
    controls[name].set("clickable", "false")

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize("value", ["", "TRUE", "0"])
def test_close_enabled_state_must_be_explicit(value):
    root, _, _, controls = dialog_xml()
    controls["aerr_close"].set("enabled", value)

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize(
    "location", ["dialog", "container", "alertTitle", "aerr_close", "aerr_wait"]
)
@pytest.mark.parametrize(
    "bounds", ["", "[-1,0][10,10]", "[10,10][10,20]", "[0,0][16385,20]"]
)
def test_observed_bounds_must_be_valid(location, bounds):
    root, dialog, container, controls = dialog_xml()
    target = {"dialog": dialog, "container": container, **controls}[location]
    target.set("bounds", bounds)

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize("name", ["alertTitle", "aerr_close", "aerr_wait"])
def test_controls_stay_inside_dialog_and_shared_container(name):
    root, _, _, controls = dialog_xml()
    controls[name].set("bounds", "[0,0][20,20]")

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


def test_shared_container_cannot_exclude_close_inside_outer_dialog():
    root, _, container, _ = dialog_xml()
    container.set("bounds", "[480,437][1439,550]")

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


@pytest.mark.parametrize("name", ["alertTitle", "aerr_close", "aerr_wait"])
def test_controls_cannot_be_assembled_across_top_level_windows(name):
    root, _, container, controls = dialog_xml()
    container.remove(controls[name])
    other = ET.SubElement(
        root,
        "node",
        {"package": "android", "bounds": "[0,0][1920,1080]"},
    )
    other.append(controls[name])

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


def test_error_dialog_cannot_include_anr_wait_control():
    root, _, _, _ = dialog_xml(anr=True)

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=False)


def test_disabled_close_does_not_allow_incomplete_dialog():
    root, _, container, controls = dialog_xml()
    controls["aerr_close"].set("enabled", "false")
    container.remove(controls["alertTitle"])

    with pytest.raises(ValueError):
        system_ui_error_close_point(ET.tostring(root), anr=True)


def test_unrelated_repeated_resource_ids_do_not_change_dialog_identity():
    root, _, container, _ = dialog_xml()
    for _ in range(2):
        ET.SubElement(
            container,
            "node",
            {"package": "android", "resource-id": "android:id/content"},
        )

    assert system_ui_error_close_point(ET.tostring(root), anr=True) == (959, 565)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<hierarchy>",
        b"<hierarchy><node></hierarchy>",
        b"<hierarchy></hierarchy>",
        b"<other></other>",
        b"\xff",
        b" " * (1024 * 1024 + 1),
        "中" * (1024 * 1024 // 3 + 1),
    ],
    ids=[
        "empty",
        "truncated",
        "mismatched",
        "no-controls",
        "wrong-root",
        "invalid-utf8",
        "large-bytes",
        "large-text",
    ],
)
def test_unreadable_or_oversized_hierarchy_is_rejected(data):
    with pytest.raises(ValueError):
        system_ui_error_close_point(data, anr=True)


def test_uiautomator_status_line_outside_xml_is_accepted():
    root, _, _, _ = dialog_xml()
    data = ET.tostring(root) + b"\nUI hierchary dumped to: /proc/self/fd/1\n"

    assert system_ui_error_close_point(data, anr=True) == (959, 565)


def test_title_and_buttons_can_use_separate_android_layouts():
    root, _, container, controls = dialog_xml()
    for name in ("alertTitle", "aerr_close"):
        container.remove(controls[name])
        wrapper = ET.SubElement(
            container,
            "node",
            {
                "package": "android",
                "class": "android.widget.LinearLayout",
                "bounds": "[480,437][1439,685]",
            },
        )
        wrapper.append(controls[name])

    assert system_ui_error_close_point(ET.tostring(root), anr=True) == (959, 565)


@pytest.mark.parametrize(
    "wrapper",
    [
        b"<!DOCTYPE hierarchy [<!ENTITY title 'arbitrary'>]>%s",
        b"<extra/>%s",
        b"%s<extra/>",
        b"%s<hierarchy></hierarchy>",
    ],
    ids=["doctype", "extra-prefix", "extra-suffix", "second-hierarchy"],
)
def test_extra_xml_or_entity_declarations_are_rejected(wrapper):
    root, _, _, _ = dialog_xml()

    with pytest.raises(ValueError):
        system_ui_error_close_point(wrapper % ET.tostring(root), anr=True)


@pytest.mark.parametrize(
    ("value", "current_user", "expected"),
    [
        ("{}", 0, "unread"),
        ("{10=null}", 0, "unread"),
        ("{0=null}", 0, "absent"),
        ("{0=[WallpaperColors: ff000000 ff111111 h: 0], 10=null}", 0, "present"),
        ("{0=[WallpaperColors: ff000000 ff111111 h: 0], 10=null}", 10, "absent"),
        ("{0=null, 10=[WallpaperColors: ff222222 h: 3]}", 0, "absent"),
    ],
)
def test_sparse_wallpaper_colors_identify_only_current_user(
    value, current_user, expected
):
    assert wallpaper_color_state(value, current_user) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "null",
        "[WallpaperColors: ff000000 h: 0]",
        "unknown",
        "{0=null",
        "0=null}",
        "{0=null}trailing",
        "{ 0=null}",
        "{0=null }",
        "{0 =null}",
        "{0=NULL}",
        "{0=null,0=null}",
        "{0=null, 0=null}",
        "{0=null, 10=unknown}",
        "{0=null, 10=[WallpaperColors: ff000000 h: 0]extra}",
        "{01=null}",
        "{-1=null}",
        "{2147483648=null}",
        "{0=[WallpaperColors: h: 0]}",
        "{0=[WallpaperColors: 0xff000000 h: 0]}",
        "{0=[WallpaperColors: FF000000 h: 0]}",
        "{0=[WallpaperColors: fffffffff h: 0]}",
        "{0=[WallpaperColors: ff000000  h: 0]}",
        "{0=[WallpaperColors: ff000000 h: unknown]}",
        "{0=[WallpaperColors: ff000000 h: +1]}",
        "{0=[WallpaperColors: ff000000 h: 01]}",
        "{0=[WallpaperColors: ff000000 h: -0]}",
        "{0=[WallpaperColors: ff000000 h: 2147483648]}",
        "{0=[WallpaperColors: ff000000 h: -2147483649]}",
    ],
)
def test_unknown_or_malformed_wallpaper_dump_does_not_claim_absent_colors(value):
    assert wallpaper_color_state(value, 0) is None


@pytest.mark.parametrize("hints", ["0", "7", "-2147483648", "2147483647"])
def test_wallpaper_color_serialization_accepts_java_hex_and_integer_formats(hints):
    value = "{0=[WallpaperColors: 0 a ffabcdef h: " + hints + "]}"

    assert wallpaper_color_state(value, 0) == "present"


@pytest.mark.parametrize("current_user", [-1, 2147483648, True, "0", None])
def test_unknown_current_user_cannot_be_classified_as_unread(current_user):
    assert wallpaper_color_state("{0=null}", current_user) is None


def test_duplicate_other_user_invalidates_the_whole_wallpaper_map():
    value = "{0=null, 10=null, 10=[WallpaperColors: ff123456 h: 0]}"

    assert wallpaper_color_state(value, 0) is None
