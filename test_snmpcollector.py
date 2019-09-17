from easysnmp import SNMPVariable

from snmpcollector import _apply_expression_to_results, _convert_counters_to_values


def test_apply_expression_snmpget():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='5', value='68000', snmp_type='GAUGE'),
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'p': 'snmp.test123.asdf', 'v': 68000.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_apply_expression_snmpget_add():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='5', value='68000', snmp_type='GAUGE'),
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value='200', snmp_type='GAUGE'),
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1 + $2'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'p': 'snmp.test123.asdf', 'v': 68200.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_apply_expression_snmpwalk():
    results = [
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value='60000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='2', value='61000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='3', value='62000', snmp_type='GAUGE'),
        ],
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'p': 'snmp.test123.asdf.1', 'v': 60000.0 },
        { 'p': 'snmp.test123.asdf.2', 'v': 61000.0 },
        { 'p': 'snmp.test123.asdf.3', 'v': 62000.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_apply_expression_expression_add():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.8', oid_index='23', value='500', snmp_type='GAUGE'),
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value='60000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='2', value='61000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='3', value='62000', snmp_type='GAUGE'),
        ],
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1 + $2'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'p': 'snmp.test123.asdf.1', 'v': 60500.0 },
        { 'p': 'snmp.test123.asdf.2', 'v': 61500.0 },
        { 'p': 'snmp.test123.asdf.3', 'v': 62500.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_apply_expression_snmpwalk_missing_value_walk():
    results = [
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value='60000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='2', value='61000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='3', value='62000', snmp_type='GAUGE'),
        ],
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.2.2', oid_index='1', value='10', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.2.2', oid_index='2', value='10', snmp_type='GAUGE'),
        ],
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1 / $2'
    output_path = 'snmp.test123.asdf'
    expected_result = [
        { 'p': 'snmp.test123.asdf.1', 'v': 6000.0 },
        { 'p': 'snmp.test123.asdf.2', 'v': 6100.0 },
    ]
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_apply_expression_snmpwalk_missing_value_get():
    results = [
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value='60000', snmp_type='GAUGE'),
        SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.2.2', oid_index='1', value=None, snmp_type='GAUGE'),
    ]
    methods = ['walk' if isinstance(x, list) else 'get' for x in results]
    expression = '$1 / $2'
    output_path = 'snmp.test123.asdf'
    expected_result = []
    assert _apply_expression_to_results(results, methods, expression, output_path) == expected_result

def test_convert_counters_no_counters_no_change():
    """ If there are no counters, nothing should change """
    now = 1234567890.123456
    results = [
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='1', value='60000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='2', value='61000', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.1.3', oid_index='3', value='62000', snmp_type='GAUGE'),
        ],
        [
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.2.2', oid_index='1', value='10', snmp_type='GAUGE'),
            SNMPVariable(oid='1.3.6.1.4.1.2021.13.16.2.2.2', oid_index='2', value='10', snmp_type='GAUGE'),
        ],
    ]
    assert _convert_counters_to_values(results, now, "ASDF/1234") == results

def test_convert_counters_counter():
    """ First expression should be empty, next ones should work """
    now = 1234567890.123456

    results_0 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.16', oid_index='1', value='1000', snmp_type='COUNTER')]
    expected_0 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.16', oid_index='1', value=None, snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_0, now, "ASDF/1234") == expected_0

    results_1 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.16', oid_index='1', value='2000.0', snmp_type='COUNTER')]
    expected_1 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.16', oid_index='1', value='1000.0', snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_1, now + 1.0, "ASDF/1234") == expected_1

    results_2 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.16', oid_index='1', value='2300.0', snmp_type='COUNTER')]
    expected_2 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.16', oid_index='1', value='100.0', snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_2, now + 1.0 + 3.0, "ASDF/1234") == expected_2

def test_convert_counters_overflow():
    """ First expression should be empty, next ones should work """
    now = 1234567890.123456

    results_0 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value='123000.0', snmp_type='COUNTER')]
    expected_0 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value=None, snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_0, now, "ASDF/1234") == expected_0

    results_1 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value='234000.0', snmp_type='COUNTER')]
    expected_1 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value='111000.0', snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_1, now + 1.0, "ASDF/1234") == expected_1

    results_2 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value='1000.0', snmp_type='COUNTER')]
    expected_2 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value=None, snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_2, now + 1.0 + 3.0, "ASDF/1234") == expected_2

    results_3 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value='2000.0', snmp_type='COUNTER')]
    expected_3 = [SNMPVariable(oid='.1.3.6.1.2.1.2.2.1.17', oid_index='1', value='500.0', snmp_type='COUNTER_PER_S')]
    assert _convert_counters_to_values(results_3, now + 1.0 + 3.0 + 2.0, "ASDF/1234") == expected_3
