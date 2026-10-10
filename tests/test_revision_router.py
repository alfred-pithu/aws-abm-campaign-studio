from src.agents.revision_router import route_revision


def test_less_salesy_routes_to_content():
    assert route_revision("make this less salesy") == "content"


def test_change_image_routes_to_asset():
    assert route_revision("change the image") == "asset"


def test_audience_angle_routes_to_strategy():
    assert route_revision("the audience angle is wrong") == "strategy"
