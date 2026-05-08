from backend.services.theme_alias_resolver import ThemeAliasResolver


def test_lu_desc_alias_maps_to_multiple_normalized_themes():
    resolver = ThemeAliasResolver()

    themes = resolver.resolve_text("半导体洁净室+海外EPC+城市更新")
    names = [theme["normalized_theme_name"] for theme in themes]

    assert "半导体" in names
    assert "芯片概念" in names
    assert "一带一路" in names
    assert "城市更新" in names


def test_generic_theme_is_marked_for_penalty():
    resolver = ThemeAliasResolver()

    resolved = resolver.resolve_one("华为概念")

    assert resolved["normalized_theme_name"] == "华为概念"
    assert resolved["is_generic"] is True
    assert resolved["penalty"] < 0


def test_compute_power_alias_maps_to_compute_rental():
    resolver = ThemeAliasResolver()

    names = [item["normalized_theme_name"] for item in resolver.resolve_many("算力")]

    assert "算力租赁" in names
