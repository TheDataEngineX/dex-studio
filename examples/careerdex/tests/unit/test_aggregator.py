from careerdex.services.aggregator.base import SourceRegistry, normalize_company


def test_normalize_company():
    assert normalize_company("Google") == "google"
    assert normalize_company("Meta Platforms") == "metaplatforms"
    assert normalize_company("McDonald's") == "mcdonalds"
    assert normalize_company("ABC 123") == "abc123"


def test_source_registry_list():
    SourceRegistry.autodiscover()
    sources = SourceRegistry.list_sources()
    assert "linkedin" in sources
    assert "indeed" in sources
    assert "greenhouse" in sources
    assert "lever" in sources
    assert "workday" in sources


def test_source_registry_get():
    SourceRegistry.autodiscover()
    li = SourceRegistry.get("linkedin")
    assert li is not None
    assert li.name == "linkedin"
