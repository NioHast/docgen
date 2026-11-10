# Style

Halaman ini menjelaskan style inti yang dipakai pipeline dan asal
`reference.docx`. Kontrak style ada di
[contracts/docx-api.md](../contracts/docx-api.md).

Style inti yang dipakai pipeline:

- `Normal`, `Heading1` sampai `Heading9`;
- `TOCHeading`, `TOC1`, `TOC2`, `TOC3`;
- `Caption`, `TableCaption`, `ImageCaption`, `Figure`;
- `Bibliography`, `SourceCode`, `VerbatimChar`, `HTMLCode`,
  `HTMLPreformatted`;
- `IstilahAsing`, `IstilahReview`;
- style sampul seperti `CoverTitle`, `CoverSubtitle`, `CoverName`,
  `CoverInstitution`, dan `CoverImage`.

`style_reference` menghasilkan `reference.docx` turunan dari `format.yml`.
Sumber `reference.docx` di `src/docgen/data/` tidak pernah ditimpa.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [package.md](package.md) untuk part `word/styles.xml`.
- [fields.md](fields.md) untuk field yang memakai style TOC.
- [terms.md](terms.md) untuk style `IstilahAsing` dan `IstilahReview`.
- [../formats.md](../formats.md) untuk `format.yml`.
