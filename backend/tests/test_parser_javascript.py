import pytest
from app.ingestion.parsers.javascript import JavaScriptParser
from app.graph.schema import NodeType, RelType

def test_javascript_functions_and_classes():
    code = """
    export class PaymentGateway extends BaseGateway {
        constructor(config) {
            super();
            this.config = config;
        }
        async charge(amount) {
            return this.executeCharge(amount);
        }
    }

    export function calculateTax(amount, rate) {
        return amount * rate;
    }

    export const sanitizeInput = (input) => {
        return input.trim();
    };
    """
    parser = JavaScriptParser()
    symbols, rels = parser.parse("src/payment.js", code)

    names = {s.name: s for s in symbols}
    assert "PaymentGateway" in names
    assert names["PaymentGateway"].type == NodeType.CLASS

    assert "calculateTax" in names
    assert names["calculateTax"].type == NodeType.FUNCTION

    assert "sanitizeInput" in names
    assert names["sanitizeInput"].type == NodeType.FUNCTION

    # Check inheritance
    inherits = [r for r in rels if r.type == RelType.INHERITS]
    assert any(r.target_name == "BaseGateway" for r in inherits)

def test_javascript_imports_and_fetch_calls():
    code = """
    import { formatCurrency } from './utils';
    import axios from 'axios';

    export async function fetchBalance(accountId) {
        const response = await fetch('/api/v1/accounts/' + accountId);
        return response.json();
    }
    """
    parser = JavaScriptParser()
    symbols, rels = parser.parse("src/api.js", code)

    # Check imports
    imports = [r for r in rels if r.type == RelType.IMPORTS]
    assert any(r.target_name == "formatCurrency" for r in imports)
    assert any(r.target_name == "axios" for r in imports)

    # Check API dependencies
    deps = [r for r in rels if r.type == RelType.DEPENDS_ON]
    assert any("/api/v1/accounts/" in r.target_name for r in deps)

def test_javascript_jsx_parsing():
    code = """
    import React from 'react';
    import { Header } from './Header';

    export default function App() {
        return (
            <div className="main">
                <Header title="Dashboard" />
            </div>
        );
    }
    """
    parser = JavaScriptParser(is_jsx=True)
    symbols, rels = parser.parse("src/App.jsx", code)

    names = {s.name for s in symbols}
    assert "App" in names

    calls = [r for r in rels if r.type == RelType.CALLS]
    assert any(r.target_name == "Header" for r in calls)

def test_javascript_error_recovery():
    malformed = """
    function validFirst() { return true; }
    var broken = { invalid :::: syntax ;
    function validSecond() { return false; }
    """
    parser = JavaScriptParser()
    symbols, rels = parser.parse("src/broken.js", malformed)

    names = {s.name for s in symbols}
    assert "validFirst" in names
    assert "validSecond" in names
