//! Interface en ligne de commande : une requête JSON sur l'entrée standard,
//! une réponse JSON sur la sortie standard. Code de sortie 0 en cas de succès,
//! 2 en cas de requête invalide.

use std::io::{Read, Write};
use std::process::ExitCode;

use lexverif::contract::Response;
use lexverif::{handle, Request, CONTRACT_VERSION};

/// Taille maximale acceptée sur l'entrée standard (8 Mio).
const MAX_INPUT_BYTES: u64 = 8 * 1024 * 1024;

fn error(message: String) -> Response {
    Response::Error {
        contract_version: CONTRACT_VERSION,
        engine_version: lexverif::verify::ENGINE_VERSION,
        error: message,
    }
}

fn main() -> ExitCode {
    let mut input = String::new();
    let read = std::io::stdin()
        .take(MAX_INPUT_BYTES + 1)
        .read_to_string(&mut input);
    let (response, code) = match read {
        Err(e) => (error(format!("lecture de l'entrée impossible : {e}")), 2),
        Ok(n) if n as u64 > MAX_INPUT_BYTES => (error("entrée trop volumineuse".into()), 2),
        Ok(_) => match serde_json::from_str::<Request>(&input) {
            Ok(request) => {
                let response = handle(request);
                let code = u8::from(matches!(response, Response::Error { .. })) * 2;
                (response, code)
            }
            Err(e) => (error(format!("requête invalide : {e}")), 2),
        },
    };
    let rendered = serde_json::to_string(&response)
        .unwrap_or_else(|_| r#"{"status":"error","error":"sérialisation impossible"}"#.into());
    let mut stdout = std::io::stdout().lock();
    if writeln!(stdout, "{rendered}").is_err() {
        return ExitCode::from(3);
    }
    ExitCode::from(code)
}
