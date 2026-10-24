//! Normalisation conservatrice du texte pour la comparaison de citations.
//!
//! Règles appliquées, et seulement celles-ci :
//! 1. normalisation Unicode NFC par grappe (caractère de base + marques combinantes) ;
//! 2. apostrophes typographiques (U+2019, U+2018, U+02BC) ramenées à `'` ;
//! 3. toute suite d'espaces Unicode (dont U+00A0 et U+202F) réduite à une espace ;
//! 4. espaces de début et de fin supprimées.
//!
//! La casse, la ponctuation, les guillemets et les chiffres ne sont PAS
//! modifiés : une citation juridique doit rester littérale.

use unicode_normalization::char::is_combining_mark;
use unicode_normalization::UnicodeNormalization;

/// Texte normalisé et correspondance vers les octets du texte d'origine.
#[derive(Debug, Clone)]
pub struct Normalized {
    pub text: String,
    /// Pour chaque caractère de `text` (dans l'ordre) : (octet de début dans
    /// `text`, octet de début dans l'original, octet de fin dans l'original).
    spans: Vec<(usize, usize, usize)>,
}

fn map_char(c: char) -> char {
    match c {
        '\u{2019}' | '\u{2018}' | '\u{02BC}' => '\'',
        other => other,
    }
}

pub fn normalize(original: &str) -> Normalized {
    // 1. Découpage en grappes (base + marques combinantes) avec leurs bornes d'origine.
    let mut clusters: Vec<(usize, usize)> = Vec::new();
    for (idx, c) in original.char_indices() {
        let end = idx + c.len_utf8();
        match clusters.last_mut() {
            Some(last) if is_combining_mark(c) => last.1 = end,
            _ => clusters.push((idx, end)),
        }
    }

    let mut text = String::with_capacity(original.len());
    let mut spans = Vec::with_capacity(original.len());
    let mut pending_space: Option<(usize, usize)> = None;

    for (start, end) in clusters {
        let cluster = &original[start..end];
        for c in cluster.nfc() {
            let c = map_char(c);
            if c.is_whitespace() {
                // Une suite d'espaces devient une seule espace, rattachée à la première.
                pending_space.get_or_insert((start, end));
                continue;
            }
            if let Some((ws_start, ws_end)) = pending_space.take() {
                if !text.is_empty() {
                    spans.push((text.len(), ws_start, ws_end));
                    text.push(' ');
                }
            }
            spans.push((text.len(), start, end));
            text.push(c);
        }
    }

    Normalized { text, spans }
}

impl Normalized {
    /// Convertit un intervalle d'octets de `text` en intervalle d'octets de l'original.
    pub fn original_span(&self, start: usize, end: usize) -> Option<(usize, usize)> {
        let first = self.spans.iter().find(|(n, _, _)| *n == start)?;
        let last = self.spans.iter().rev().find(|(n, _, _)| *n < end)?;
        Some((first.1, last.2))
    }

    /// Nombre de caractères non blancs du texte normalisé.
    pub fn significant_len(&self) -> usize {
        self.text.chars().filter(|c| !c.is_whitespace()).count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collapses_unicode_whitespace_and_apostrophes() {
        let n = normalize("  L\u{2019}article\u{00A0}\u{00A0}L. 125-2\n du code ");
        assert_eq!(n.text, "L'article L. 125-2 du code");
    }

    #[test]
    fn keeps_case_and_punctuation() {
        let n = normalize("Le Code « civil »");
        assert_eq!(n.text, "Le Code « civil »");
    }

    #[test]
    fn composes_decomposed_accents() {
        // "é" décomposé (e + U+0301) doit égaler "é" précomposé.
        let n = normalize("re\u{0301}gime");
        assert_eq!(n.text, "r\u{00E9}gime");
    }

    #[test]
    fn maps_back_to_original_offsets() {
        let original = "Alpha\u{00A0}\u{00A0}be\u{0301}ta gamma";
        let n = normalize(original);
        let needle = "béta";
        let pos = n.text.find(needle);
        assert!(pos.is_some());
        let pos = pos.unwrap_or_default();
        let span = n.original_span(pos, pos + needle.len());
        assert_eq!(span.map(|(s, e)| &original[s..e]), Some("be\u{0301}ta"));
    }
}
