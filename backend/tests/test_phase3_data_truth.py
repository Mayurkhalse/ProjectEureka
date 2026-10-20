"""Targeted tests for Phase 3: Data Truth and District Invariant Reconciliation."""

import pytest
from eureka.copilot.tools import (
    normalize_district_code,
    extract_district_from_query,
    tool_district_profile,
    DistrictProfileArgs,
    CopilotPrincipal,
)
from eureka.hermes.agent_tools import _query_36_districts_from_csv


def test_query_36_districts_official_codes():
    """Verify that _query_36_districts_from_csv outputs authoritative district codes matching eureka.db."""
    data = _query_36_districts_from_csv()
    districts = {d["name_en"]: d for d in data.get("districts", [])}
    
    assert "Thane" in districts
    assert districts["Thane"]["district_code"] == "MH-04"
    assert districts["Thane"]["division_code"] == "DIV-KON"
    
    assert "Palghar" in districts
    assert districts["Palghar"]["district_code"] == "MH-03"
    assert districts["Palghar"]["division_code"] == "DIV-KON"
    
    assert "Ahilyanagar" in districts
    assert districts["Ahilyanagar"]["district_code"] == "MH-25"
    
    assert "Chhatrapati Sambhajinagar" in districts
    assert districts["Chhatrapati Sambhajinagar"]["district_code"] == "MH-17"
    
    assert "Dharashiv" in districts
    assert districts["Dharashiv"]["district_code"] == "MH-14"


def test_alias_table_resolution():
    """Verify that former names and variants resolve to official current codes via alias table."""
    # Former names
    assert normalize_district_code("Aurangabad") == "MH-17"
    assert normalize_district_code("Osmanabad") == "MH-14"
    assert normalize_district_code("Ahmednagar") == "MH-25"
    assert normalize_district_code("Ahmadnagar") == "MH-25"
    assert normalize_district_code("Bombay City") == "MH-01"
    assert normalize_district_code("Mumbai") == "MH-01"
    assert normalize_district_code("Alibag") == "MH-05"
    
    # Official names
    assert normalize_district_code("Thane") == "MH-04"
    assert normalize_district_code("Palghar") == "MH-03"
    assert normalize_district_code("Ahilyanagar") == "MH-25"
    assert normalize_district_code("Chhatrapati Sambhajinagar") == "MH-17"
    assert normalize_district_code("Dharashiv") == "MH-14"


def test_extract_district_from_natural_language_queries():
    """Verify regex and alias matching in Marathi and English queries."""
    assert extract_district_from_query("how many news are there about thane") == "MH-04"
    assert extract_district_from_query("palghar tribal welfare report") == "MH-03"
    assert extract_district_from_query("Show me stats for Aurangabad") == "MH-17"
    assert extract_district_from_query("What is happening in Osmanabad?") == "MH-14"
    assert extract_district_from_query("Status of Ahmednagar district") == "MH-25"
    assert extract_district_from_query("अहिल्यानगर मधील अहवाल") == "MH-25"
    assert extract_district_from_query("ठाणे जिल्ह्यातील कामगिरी") == "MH-04"
    assert extract_district_from_query("पालघर मधील बातमी") == "MH-03"
