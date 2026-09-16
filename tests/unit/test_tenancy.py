from dataclasses import FrozenInstanceError
import pytest
from coops.domain.tenancy import TenantId, CorrelationId

def test_str_returns_org_id():
    tenant_id = TenantId("test_org")
    assert str(tenant_id) == "test_org"

def test_empty_org_id_raises_value_error():
    with pytest.raises(ValueError):
        TenantId("")

def test_whitespace_org_id_raises_value_error():
    with pytest.raises(ValueError):
        TenantId("   ")

def test_new_generates_valid_values():
    correlation_id = CorrelationId.new()
    assert correlation_id.value

def test_str_returns_correlation_id_value():
    correlation_id = CorrelationId("test_id")
    assert str(correlation_id) == "test_id"

def test_new_generates_unique_values():
    correlation_id1 = CorrelationId.new()
    correlation_id2 = CorrelationId.new()
    assert correlation_id1 != correlation_id2

def test_correlation_id_immutability():
    correlation_id = CorrelationId.new()
    with pytest.raises(FrozenInstanceError):
        correlation_id.value = "test_id_immutable"

def test_tenant_id_immutability():
    tenant_id = TenantId("test_id")
    with pytest.raises(FrozenInstanceError):
        tenant_id.org_id = "test_id2"

@pytest.mark.parametrize("raw", ["unb-mds", "UNB-MDS", "  Unb-Mds  ", "\tunb-mds\n"])
def test_org_id_is_trimmed_and_lowercased(raw):
    """GitHub org names are case-insensitive: one org must map to one tenant."""
    tenant_id = TenantId(raw)
    assert tenant_id.org_id == "unb-mds"
    assert tenant_id == TenantId("unb-mds")
    assert hash(tenant_id) == hash(TenantId("unb-mds"))


def test_none_org_id_raises_value_error():
    with pytest.raises(ValueError):
        TenantId(None)


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_correlation_id_raises_value_error(raw):
    with pytest.raises(ValueError):
        CorrelationId(raw)
