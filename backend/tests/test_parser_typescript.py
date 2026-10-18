import pytest
from app.ingestion.parsers.typescript import TypeScriptParser
from app.graph.schema import NodeType, RelType

def test_typescript_class_and_methods():
    code = """
    export class OrderService extends BaseService implements IOrderProcessor {
        private db: Database;
        constructor(db: Database) {
            super();
            this.db = db;
        }
        async processOrder(orderId: string): Promise<OrderResult> {
            return this.db.save(orderId);
        }
    }
    """
    parser = TypeScriptParser()
    symbols, rels = parser.parse("src/services/OrderService.ts", code)

    names = {s.name: s for s in symbols}
    assert "OrderService" in names
    assert names["OrderService"].type == NodeType.CLASS
    assert names["OrderService"].language == "typescript"

    assert "processOrder" in names
    assert names["processOrder"].type == NodeType.METHOD
    assert names["processOrder"].properties.get("is_async") is True

    # Check inheritance and interface implementation
    inherits = [r for r in rels if r.type == RelType.INHERITS]
    assert any(r.target_name == "BaseService" for r in inherits)
    assert all(r.confidence == 1.0 and not r.is_inferred for r in inherits)

    implements = [r for r in rels if r.type == RelType.IMPLEMENTS]
    assert any(r.target_name == "IOrderProcessor" for r in implements)
    assert all(r.confidence == 1.0 and not r.is_inferred for r in implements)

def test_typescript_interfaces_types_and_enums():
    code = """
    interface UserProfile extends BaseProfile {
        id: string;
        username: string;
    }
    type UserId = string | number;
    enum UserRole {
        ADMIN = 'admin',
        GUEST = 'guest'
    }
    """
    parser = TypeScriptParser()
    symbols, rels = parser.parse("src/types/user.ts", code)

    names = {s.name: s for s in symbols}
    assert "UserProfile" in names
    assert "UserId" in names
    assert "UserRole" in names

    # Interface extends relationship
    inherits = [r for r in rels if r.type == RelType.INHERITS]
    assert any(r.source_name == "UserProfile" and r.target_name == "BaseProfile" for r in inherits)

def test_typescript_imports_and_exports():
    code = """
    import React, { useState, useEffect } from 'react';
    import * as auth from './auth';
    import './styles.css';
    export { helperFn } from './utils';
    """
    parser = TypeScriptParser()
    symbols, rels = parser.parse("src/components/View.ts", code)

    imports = [r for r in rels if r.type == RelType.IMPORTS]
    imported_names = {r.target_name for r in imports}
    assert "React" in imported_names
    assert "useState" in imported_names
    assert "useEffect" in imported_names
    assert "auth" in imported_names

    side_effects = [r for r in rels if r.type == RelType.DEPENDS_ON]
    assert any("./styles.css" in r.target_name for r in side_effects)

    exposes = [r for r in rels if r.type == RelType.EXPOSES]
    assert any(r.target_name == "helperFn" for r in exposes)

def test_tsx_component_and_jsx_calls():
    code = """
    import React from 'react';
    import { Avatar } from './Avatar';

    export const UserCard: React.FC<{ name: string }> = ({ name }) => {
        return (
            <div className="card">
                <Avatar userName={name} />
                <span>{name}</span>
            </div>
        );
    };
    """
    parser = TypeScriptParser(is_tsx=True)
    symbols, rels = parser.parse("src/components/UserCard.tsx", code)

    names = {s.name: s for s in symbols}
    assert "UserCard" in names
    assert names["UserCard"].type == NodeType.FUNCTION
    assert names["UserCard"].properties.get("is_component") is True

    # JSX tag <Avatar /> should create a CALLS relationship to Avatar
    calls = [r for r in rels if r.type == RelType.CALLS]
    called_names = {r.target_name for r in calls}
    assert "Avatar" in called_names
    avatar_rel = next(r for r in calls if r.target_name == "Avatar")
    assert avatar_rel.confidence == 1.0
    assert not avatar_rel.is_inferred

def test_typescript_error_recovery_on_malformed_syntax():
    malformed_code = """
    function validBefore() { return 1; }
    class BrokenClass { unclosed ( syntax here ...
    function validAfter() { return 2; }
    """
    parser = TypeScriptParser()
    # Parser should not raise exception on malformed code
    symbols, rels = parser.parse("src/broken.ts", malformed_code)

    names = {s.name for s in symbols}
    assert "validBefore" in names
    assert "validAfter" in names
