from easysnmp import SNMPVariable

from snmpcollector import _apply_expression_to_results


def test_snmpget():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='5', value=68000, snmp_type='GAUGE'),
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'path': 'snmp.test123.asdf', 'value': 68000.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_snmpget_add():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='5', value=68000, snmp_type='GAUGE'),
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value=200, snmp_type='GAUGE'),
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1 + $2'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'path': 'snmp.test123.asdf', 'value': 68200.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_snmpwalk():
    results = [
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value=60000, snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='2', value=61000, snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='3', value=62000, snmp_type='GAUGE'),
        ],
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'path': 'snmp.test123.asdf.1', 'value': 60000.0 },
        { 'path': 'snmp.test123.asdf.2', 'value': 61000.0 },
        { 'path': 'snmp.test123.asdf.3', 'value': 62000.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_expression_add():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.8', oid_index='23', value=500, snmp_type='GAUGE'),
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value=60000, snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='2', value=61000, snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='3', value=62000, snmp_type='GAUGE'),
        ],
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1 + $2'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'path': 'snmp.test123.asdf.1', 'value': 60500.0 },
        { 'path': 'snmp.test123.asdf.2', 'value': 61500.0 },
        { 'path': 'snmp.test123.asdf.3', 'value': 62500.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result
