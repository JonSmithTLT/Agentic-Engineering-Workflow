/** Presentation vocabulary pinned to S1 mapview.py, maps/rules.yaml, engine/freshness.py and the accepted MapInput.reason annotation. Unknown strings remain accepted and visible. */
export const mapVocabulary = {
  "language": [
    "Assembly",
    "Batch",
    "C",
    "C#",
    "C++",
    "CMake",
    "CSS",
    "Clojure",
    "Dart",
    "Dockerfile",
    "Elixir",
    "Erlang",
    "F#",
    "Fortran",
    "Go",
    "Groovy",
    "HTML",
    "Haskell",
    "INI",
    "JSON",
    "Java",
    "JavaScript",
    "Julia",
    "Kotlin",
    "Lua",
    "Makefile",
    "Markdown",
    "Nim",
    "OCaml",
    "Objective-C",
    "Objective-C++",
    "PHP",
    "Perl",
    "PowerShell",
    "Protocol Buffers",
    "Python",
    "R",
    "Ruby",
    "Rust",
    "SCSS",
    "SQL",
    "Scala",
    "Shell",
    "Starlark",
    "Svelte",
    "Swift",
    "SystemVerilog",
    "TOML",
    "Terraform",
    "Text",
    "TypeScript",
    "VHDL",
    "Verilog",
    "Vue",
    "XML",
    "YAML",
    "Zig",
    "reStructuredText"
  ],
  "directoryLabel": [
    "assets",
    "benchmarks",
    "ci",
    "config",
    "docs",
    "examples",
    "fixtures",
    "generated",
    "headers",
    "migrations",
    "root",
    "scripts",
    "source",
    "tests",
    "tools",
    "unknown",
    "vendor"
  ],
  "buildKind": [
    "ant",
    "autotools",
    "bazel",
    "cmake",
    "container",
    "dart",
    "deno",
    "dotnet",
    "elixir",
    "go",
    "gradle",
    "haskell",
    "make",
    "maven",
    "meson",
    "msbuild",
    "nim",
    "node",
    "php",
    "python",
    "ruby",
    "rust",
    "sbt",
    "scons",
    "swift"
  ],
  "buildStatus": [
    "listed",
    "parsed",
    "parse_failed",
    "lfs_pointer",
    "symlink",
    "capped_size",
    "capped_total"
  ],
  "entryLabel": [
    "declared",
    "convention"
  ],
  "entryRule": [
    "__main__.py",
    "*/__main__.py",
    "main.py",
    "src/main.py",
    "manage.py",
    "main.go",
    "cmd/*/main.go",
    "src/main.rs",
    "src/bin/*.rs",
    "main.c",
    "src/main.c",
    "main.cpp",
    "src/main.cpp",
    "Program.cs",
    "*/Program.cs",
    "index.js",
    "src/index.js",
    "src/index.ts",
    "src/main.ts"
  ],
  "testKind": [
    "directory",
    "file_pattern",
    "runner_config"
  ],
  "testRunner": [
    "ctest",
    "jest",
    "karma",
    "mocha",
    "nox",
    "npm test",
    "phpunit",
    "pytest",
    "rspec",
    "tox",
    "vitest"
  ],
  "testSource": [
    "convention",
    "declared"
  ],
  "gvKind": [
    "generated",
    "vendored"
  ],
  "gvSource": [
    "convention",
    "gitattributes"
  ],
  "semanticKind": [
    "clang_tidy",
    "clangd",
    "compile_database",
    "compile_flags",
    "go_workspace",
    "jsconfig",
    "mypy",
    "pyright",
    "rust_project",
    "tsconfig"
  ],
  "semanticSource": [
    "convention",
    "declared"
  ],
  "capSection": [
    "directories",
    "languages",
    "build_descriptors",
    "entry_point_candidates",
    "test_candidates",
    "generated_and_vendor",
    "semantic_prerequisites",
    "limits_and_omissions"
  ],
  "capField": [
    "rows_omitted",
    "submodules_omitted",
    "unknown_extensions_omitted",
    "omitted"
  ],
  "parseCode": [
    "not_utf8",
    "invalid_toml",
    "invalid_json",
    "invalid_ini"
  ],
  "unsupportedReason": [
    "symlink"
  ],
  "objectFormat": [
    "sha1",
    "sha256"
  ],
  "generatorName": [
    "structural"
  ],
  "inputReason": [
    "capped_size",
    "capped_total"
  ],
  "architectureBasis": [
    "external",
    "not-applicable",
    "authoritative-source"
  ],
  "architectureScope": [
    "declared paths",
    "whole tree"
  ]
} as const;
