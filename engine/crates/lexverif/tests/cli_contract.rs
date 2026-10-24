//! Tests du contrat JSON via le binaire, sur un texte réel (article L5422-1
//! du code du travail, version LEGIARTI000048590547, dump LEGI du 2026-10-23).

use std::io::Write;
use std::process::{Command, Stdio};

use serde_json::{json, Value};

const TEXT: &str = "I.-Ont droit à l'allocation d'assurance les travailleurs aptes au travail et recherchant un emploi qui satisfont à des conditions d'âge et d'activité antérieure, et dont :\n1° Soit la privation d'emploi est involontaire, ou assimilée à une privation involontaire par les accords relatifs à l'assurance chômage mentionnés à l'article L. 5422-20 ;";

fn run(request: &Value) -> (Value, i32) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_lexverif"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap_or_else(|e| unreachable!("lancement impossible : {e}"));
    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(request.to_string().as_bytes())
            .unwrap_or_else(|e| unreachable!("écriture impossible : {e}"));
    }
    let output = child
        .wait_with_output()
        .unwrap_or_else(|e| unreachable!("attente impossible : {e}"));
    let value: Value = serde_json::from_slice(&output.stdout).unwrap_or(Value::Null);
    (value, output.status.code().unwrap_or(-1))
}

fn request(quote: &str, as_of: &str, candidate_id: Option<&str>) -> Value {
    let period = json!({
        "official_id": "LEGIARTI000048590547",
        "valid_from": "2025-01-01",
        "valid_to": null,
        "status_raw": "VIGUEUR"
    });
    let previous = json!({
        "official_id": "LEGIARTI000046774640",
        "valid_from": "2022-12-23",
        "valid_to": "2025-01-01",
        "status_raw": "MODIFIE"
    });
    json!({
        "contract_version": "1",
        "command": "verify_citation",
        "payload": {
            "citation": {
                "official_id": candidate_id.unwrap_or("LEGIARTI000048590547"),
                "quote": quote,
                "as_of": as_of,
                "territory": null
            },
            "candidate": if candidate_id.is_some() { Value::Null } else { json!({
                "official_id": "LEGIARTI000048590547",
                "text": TEXT,
                "period": period,
                "territorial_scope": null
            })},
            "sibling_versions": [previous, period]
        }
    })
}

fn outcome(response: &Value, check: &str) -> String {
    response["result"]["checks"]
        .as_array()
        .and_then(|checks| checks.iter().find(|c| c["check"] == check))
        .and_then(|c| c["outcome"].as_str())
        .unwrap_or("ABSENT")
        .to_string()
}

#[test]
fn literal_quote_is_found_with_offsets() {
    let quote = "les travailleurs aptes au travail et recherchant un emploi";
    let (response, code) = run(&request(quote, "2026-10-24", None));
    assert_eq!(code, 0);
    assert_eq!(outcome(&response, "PASSAGE_PRESENT"), "OK");
    assert_eq!(outcome(&response, "APPLICABILITE_TEMPORELLE"), "OK");
    assert_eq!(outcome(&response, "TERRITOIRE"), "INDETERMINE");
    assert_eq!(response["result"]["verdict"], "INCERTAIN");
    let start = response["result"]["quote_span"]["start"]
        .as_u64()
        .unwrap_or(0) as usize;
    let end = response["result"]["quote_span"]["end"]
        .as_u64()
        .unwrap_or(0) as usize;
    assert_eq!(&TEXT[start..end], quote);
}

#[test]
fn quote_spanning_paragraphs_and_elision() {
    let quote = "conditions d'âge et d'activité antérieure, et dont : 1° Soit la privation d'emploi [...] mentionnés à l'article L. 5422-20";
    let (response, _) = run(&request(quote, "2026-10-24", None));
    assert_eq!(outcome(&response, "PASSAGE_PRESENT"), "OK");
}

#[test]
fn elision_segments_must_be_in_order() {
    let quote = "mentionnés à l'article L. 5422-20 [...] les travailleurs aptes au travail";
    let (response, _) = run(&request(quote, "2026-10-24", None));
    assert_eq!(outcome(&response, "PASSAGE_PRESENT"), "ECHEC");
    assert_eq!(response["result"]["verdict"], "NON_CONFORME");
}

#[test]
fn case_change_is_not_tolerated() {
    let (response, _) = run(&request(
        "LES TRAVAILLEURS APTES AU TRAVAIL ET RECHERCHANT",
        "2026-10-24",
        None,
    ));
    assert_eq!(outcome(&response, "PASSAGE_PRESENT"), "ECHEC");
}

#[test]
fn too_short_quote_is_indeterminate() {
    let (response, _) = run(&request("travail", "2026-10-24", None));
    assert_eq!(outcome(&response, "PASSAGE_PRESENT"), "INDETERMINE");
    assert_eq!(response["result"]["verdict"], "INCERTAIN");
}

#[test]
fn date_before_version_names_the_applicable_one() {
    let (response, _) = run(&request(
        "les travailleurs aptes au travail et recherchant",
        "2024-06-01",
        None,
    ));
    assert_eq!(outcome(&response, "APPLICABILITE_TEMPORELLE"), "ECHEC");
    assert_eq!(
        response["result"]["resolution_at_date"]["official_id"],
        "LEGIARTI000046774640"
    );
}

#[test]
fn unknown_identifier_is_rejected() {
    let (response, _) = run(&request(
        "les travailleurs aptes au travail",
        "2026-10-24",
        Some("LEGIARTI000099999999"),
    ));
    assert_eq!(outcome(&response, "SOURCE_IDENTIFIEE"), "OK");
    assert_eq!(outcome(&response, "IDENTIFIANT_RESOLU"), "ECHEC");
    assert_eq!(response["result"]["verdict"], "NON_CONFORME");
}

#[test]
fn non_deterministic_checks_are_never_reported_as_passed() {
    let (response, _) = run(&request(
        "les travailleurs aptes au travail et recherchant",
        "2026-10-24",
        None,
    ));
    assert_eq!(outcome(&response, "ADEQUATION_RAISONNEMENT"), "NON_EVALUE");
    assert_eq!(outcome(&response, "CONTRADICTIONS"), "NON_EVALUE");
}

#[test]
fn wrong_contract_version_and_unknown_fields_are_refused() {
    let mut req = request("x", "2026-10-24", None);
    req["contract_version"] = json!("2");
    let (response, code) = run(&req);
    assert_eq!(code, 2);
    assert_eq!(response["status"], "error");

    let mut req = request("x", "2026-10-24", None);
    req["payload"]["citation"]["injected"] = json!(true);
    let (response, code) = run(&req);
    assert_eq!(code, 2);
    assert_eq!(response["status"], "error");
}

#[test]
fn malformed_json_is_refused() {
    let (response, code) = run(&json!("pas un objet"));
    assert_eq!(code, 2);
    assert_eq!(response["status"], "error");
}
