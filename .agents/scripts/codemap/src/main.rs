use serde::Deserialize;
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

// ── pyproject.toml schema (partial) ──────────────────────────────────────────

#[derive(Deserialize, Debug)]
struct PyProject {
    project: Option<ProjectMeta>,
    tool: Option<ToolSection>,
}

#[derive(Deserialize, Debug)]
struct ProjectMeta {
    name: Option<String>,
}

#[derive(Deserialize, Debug)]
struct ToolSection {
    hatch: Option<HatchSection>,
}

#[derive(Deserialize, Debug)]
struct HatchSection {
    build: Option<HatchBuild>,
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "kebab-case")]
struct HatchBuild {
    dev_mode_dirs: Option<Vec<String>>,
}

// ── Data models ──────────────────────────────────────────────────────────────

/// A parsed polylith component (a directory with __init__.py).
struct ComponentInfo {
    filepath: String,
    summary: String,
    public_api: Vec<String>,
    dependencies: BTreeSet<String>,
}

/// A parsed Python module (a single .py file).
struct ModuleInfo {
    filepath: String,
    summary: String,
    dependencies: BTreeSet<String>,
}

// ── Main ─────────────────────────────────────────────────────────────────────

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: codemap <project_root> <output_csv>");
        std::process::exit(1);
    }
    let project_root = PathBuf::from(&args[1]);
    let output_path = PathBuf::from(&args[2]);

    // ── Read pyproject.toml ──────────────────────────────────────────────
    let pyproject_path = project_root.join("pyproject.toml");
    let pyproject_content = fs::read_to_string(&pyproject_path).unwrap_or_else(|e| {
        eprintln!("✗ Cannot read {}: {}", pyproject_path.display(), e);
        std::process::exit(1);
    });

    let pyproject: PyProject = toml::from_str(&pyproject_content).unwrap_or_else(|e| {
        eprintln!("✗ Cannot parse {}: {}", pyproject_path.display(), e);
        std::process::exit(1);
    });

    let project_name = pyproject
        .project
        .as_ref()
        .and_then(|p| p.name.as_deref())
        .unwrap_or_else(|| {
            eprintln!("✗ No [project].name found in pyproject.toml");
            std::process::exit(1);
        })
        .to_string();

    let dev_mode_dirs: Vec<String> = pyproject
        .tool
        .as_ref()
        .and_then(|t| t.hatch.as_ref())
        .and_then(|h| h.build.as_ref())
        .and_then(|b| b.dev_mode_dirs.clone())
        .unwrap_or_else(|| vec!["components".into(), "bases".into(), "development".into()]);

    eprintln!("  project  : {}", project_name);
    eprintln!("  dev dirs : {:?}", dev_mode_dirs);

    // ── Derive the import prefix used for dependency detection ───────────
    // e.g. project_name = "aer" → imports look like `from aer.xxx import ...`
    let import_prefix = format!("from {}.", project_name);
    let import_prefix_abs = format!("import {}.", project_name);
    let prefix_skip_from = import_prefix.len(); // chars to skip after "from aer."
    let prefix_skip_import = import_prefix_abs.len(); // chars to skip after "import aer."

    // ── Discover directories ─────────────────────────────────────────────
    // Polylith convention: components/<name>/ and bases/<name>/ hold the bricks
    // "development" and "." are extra source roots (scripts, top-level modules)
    let mut component_dirs: Vec<PathBuf> = Vec::new();
    let mut standalone_dirs: Vec<PathBuf> = Vec::new();

    for dir_name in &dev_mode_dirs {
        let dir = if dir_name == "." {
            // Skip root dir itself – we don't want to walk everything
            continue;
        } else {
            project_root.join(dir_name)
        };

        if !dir.exists() {
            continue;
        }

        // Check if this dir contains a namespace package (e.g. components/aer/)
        let ns_dir = dir.join(&project_name);
        if ns_dir.exists() && ns_dir.is_dir() {
            // This is a polylith brick root (components/aer/ or bases/aer/)
            component_dirs.push(ns_dir);
        } else {
            // Standalone source directory (like development/)
            standalone_dirs.push(dir);
        }
    }

    // Also add test/ if it exists
    let test_dir = project_root.join("test");
    if test_dir.exists() {
        standalone_dirs.push(test_dir);
    }

    let mut components: Vec<ComponentInfo> = Vec::new();
    let mut modules: Vec<ModuleInfo> = Vec::new();

    // ── Parse polylith components ────────────────────────────────────────
    for comp_root in &component_dirs {
        parse_components(
            comp_root,
            &project_root,
            &project_name,
            prefix_skip_from,
            prefix_skip_import,
            &import_prefix,
            &import_prefix_abs,
            &mut components,
            &mut modules,
        );
    }

    // ── Parse standalone files ───────────────────────────────────────────
    for dir in &standalone_dirs {
        parse_standalone_files(
            dir,
            &project_root,
            prefix_skip_from,
            prefix_skip_import,
            &import_prefix,
            &import_prefix_abs,
            &mut modules,
        );
    }

    // ── Write output ─────────────────────────────────────────────────────
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent).ok();
    }
    write_csv(&output_path, &components, &modules).expect("Failed to write CSV");

    eprintln!(
        "✓ Wrote {} components + {} modules to {}",
        components.len(),
        modules.len(),
        output_path.display()
    );
}

// ── Component parsing ────────────────────────────────────────────────────────

fn parse_components(
    comp_root: &Path,
    project_root: &Path,
    project_name: &str,
    prefix_skip_from: usize,
    prefix_skip_import: usize,
    import_prefix: &str,
    import_prefix_abs: &str,
    components: &mut Vec<ComponentInfo>,
    modules: &mut Vec<ModuleInfo>,
) {
    let mut entries: Vec<_> = fs::read_dir(comp_root)
        .unwrap()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().map(|ft| ft.is_dir()).unwrap_or(false))
        .filter(|e| {
            e.file_name()
                .to_str()
                .map(|n| !n.starts_with('_'))
                .unwrap_or(false)
        })
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let comp_dir = entry.path();
        let init_path = comp_dir.join("__init__.py");
        if !init_path.exists() {
            continue;
        }

        let rel_path = pathdiff(&comp_dir, project_root);
        let init_content = fs::read_to_string(&init_path).unwrap_or_default();

        let public_api = extract_all_names(&init_content);
        let init_summary = extract_docstring(&init_content);
        let init_deps = extract_dependencies(
            &init_content,
            prefix_skip_from,
            prefix_skip_import,
            import_prefix,
            import_prefix_abs,
        );

        let mut comp_deps = init_deps;

        // Parse all .py files inside the component
        let mut py_files: Vec<_> = fs::read_dir(&comp_dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                name.ends_with(".py") && name != "__init__.py"
            })
            .collect();
        py_files.sort_by_key(|e| e.file_name());

        for py_entry in py_files {
            let py_path = py_entry.path();
            let py_rel = pathdiff(&py_path, project_root);
            let content = fs::read_to_string(&py_path).unwrap_or_default();
            let py_summary = extract_docstring(&content);
            let py_deps = extract_dependencies(
                &content,
                prefix_skip_from,
                prefix_skip_import,
                import_prefix,
                import_prefix_abs,
            );

            modules.push(ModuleInfo {
                filepath: py_rel,
                summary: py_summary,
                dependencies: py_deps.clone(),
            });

            for dep in py_deps {
                comp_deps.insert(dep);
            }
        }

        // Remove self-references
        let comp_name = entry.file_name().to_string_lossy().to_string();
        comp_deps.remove(&comp_name);

        let summary = if !init_summary.is_empty() {
            init_summary
        } else {
            format!("{} component", comp_name.replace('_', " "))
        };

        components.push(ComponentInfo {
            filepath: rel_path,
            summary,
            public_api,
            dependencies: comp_deps,
        });
    }

    // Also handle the top-level __init__.py in the namespace dir itself
    let ns_init = comp_root.join("__init__.py");
    if ns_init.exists() {
        let content = fs::read_to_string(&ns_init).unwrap_or_default();
        if !content.trim().is_empty() {
            let rel_path = pathdiff(&ns_init, project_root);
            let summary = extract_docstring(&content);
            let deps = extract_dependencies(
                &content,
                prefix_skip_from,
                prefix_skip_import,
                import_prefix,
                import_prefix_abs,
            );
            modules.push(ModuleInfo {
                filepath: rel_path,
                summary: if summary.is_empty() {
                    format!("{} namespace package", project_name)
                } else {
                    summary
                },
                dependencies: deps,
            });
        }
    }
}

// ── Standalone file parsing ──────────────────────────────────────────────────

fn parse_standalone_files(
    dir: &Path,
    project_root: &Path,
    prefix_skip_from: usize,
    prefix_skip_import: usize,
    import_prefix: &str,
    import_prefix_abs: &str,
    modules: &mut Vec<ModuleInfo>,
) {
    for entry in WalkDir::new(dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| {
            e.file_type().is_file()
                && e.path()
                    .extension()
                    .map(|ext| ext == "py")
                    .unwrap_or(false)
                && !e.path().to_string_lossy().contains("__pycache__")
        })
    {
        let path = entry.path();
        let rel_path = pathdiff(path, project_root);
        let content = fs::read_to_string(path).unwrap_or_default();
        let summary = extract_docstring(&content);
        let deps = extract_dependencies(
            &content,
            prefix_skip_from,
            prefix_skip_import,
            import_prefix,
            import_prefix_abs,
        );

        modules.push(ModuleInfo {
            filepath: rel_path,
            summary,
            dependencies: deps,
        });
    }
}

// ── Python source parsing helpers ────────────────────────────────────────────

/// Extract names from `__all__ = [...]` in a Python file.
fn extract_all_names(content: &str) -> Vec<String> {
    let mut names = Vec::new();

    // Collect the full __all__ = [...] text, handling multiline
    let mut in_all = false;
    let mut bracket_depth: i32 = 0;
    let mut all_text = String::new();

    for line in content.lines() {
        let trimmed = line.trim();

        if !in_all {
            if trimmed.starts_with("__all__") && trimmed.contains('[') {
                in_all = true;
                if let Some(idx) = line.find('[') {
                    all_text.push_str(&line[idx..]);
                    bracket_depth += line[idx..].matches('[').count() as i32;
                    bracket_depth -= line[idx..].matches(']').count() as i32;
                }
                if bracket_depth <= 0 {
                    break;
                }
            }
        } else {
            all_text.push_str(trimmed);
            bracket_depth += trimmed.matches('[').count() as i32;
            bracket_depth -= trimmed.matches(']').count() as i32;
            if bracket_depth <= 0 {
                break;
            }
        }
    }

    // Find all quoted strings in the __all__ text
    let mut i = 0;
    let bytes = all_text.as_bytes();
    while i < bytes.len() {
        if bytes[i] == b'"' || bytes[i] == b'\'' {
            let quote = bytes[i];
            i += 1;
            let start = i;
            while i < bytes.len() && bytes[i] != quote {
                i += 1;
            }
            if i < bytes.len() {
                let name = &all_text[start..i];
                if !name.is_empty() {
                    names.push(name.to_string());
                }
            }
            i += 1;
        } else {
            i += 1;
        }
    }

    names
}

/// Extract the module docstring (first triple-quoted string or class/def docstring).
fn extract_docstring(content: &str) -> String {
    let trimmed = content.trim_start();

    // Try triple-quoted docstring at file level
    for quote in &["\"\"\"", "'''"] {
        if trimmed.starts_with(quote) {
            let rest = &trimmed[3..];
            if let Some(end_idx) = rest.find(quote) {
                let doc = rest[..end_idx].trim();
                let summary = first_line_or_paragraph(doc);
                return escape_csv(&summary);
            }
        }
    }

    // If file starts with class/def, try to extract its docstring
    for line in trimmed.lines() {
        let line_trimmed = line.trim();
        if line_trimmed.is_empty()
            || line_trimmed.starts_with('#')
            || line_trimmed.starts_with("import")
            || line_trimmed.starts_with("from")
        {
            continue;
        }
        if line_trimmed.starts_with("class ") || line_trimmed.starts_with("def ") {
            let after_def = trimmed.find(line_trimmed).unwrap_or(0) + line_trimmed.len();
            let remaining = trimmed[after_def..].trim_start();
            for quote in &["\"\"\"", "'''"] {
                if remaining.starts_with(quote) {
                    let rest = &remaining[3..];
                    if let Some(end_idx) = rest.find(quote) {
                        let doc = rest[..end_idx].trim();
                        let summary = first_line_or_paragraph(doc);
                        return escape_csv(&summary);
                    }
                }
            }
            break;
        }
        break;
    }

    String::new()
}

fn first_line_or_paragraph(doc: &str) -> String {
    for line in doc.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }
    String::new()
}

/// Extract `<project_name>.*` import dependencies from a Python file.
/// Returns a set of component names (the first segment after the project prefix).
fn extract_dependencies(
    content: &str,
    prefix_skip_from: usize,
    prefix_skip_import: usize,
    import_prefix: &str,
    import_prefix_abs: &str,
) -> BTreeSet<String> {
    let mut deps = BTreeSet::new();

    for line in content.lines() {
        let trimmed = line.trim();

        // Match: from <project>.<component> import ...
        if trimmed.starts_with(import_prefix) {
            let rest = &trimmed[prefix_skip_from..];
            if let Some(component) = rest.split(|c: char| c == '.' || c == ' ').next() {
                if !component.is_empty() {
                    deps.insert(component.to_string());
                }
            }
        }
        // Match: import <project>.<component>
        else if trimmed.starts_with(import_prefix_abs) {
            let rest = &trimmed[prefix_skip_import..];
            if let Some(component) =
                rest.split(|c: char| c == '.' || c == ' ' || c == ',').next()
            {
                if !component.is_empty() {
                    deps.insert(component.to_string());
                }
            }
        }
    }

    deps
}

// ── CSV output ───────────────────────────────────────────────────────────────

fn escape_csv(s: &str) -> String {
    s.replace('\n', " ").replace('\r', "").replace('"', "'")
}

fn write_csv(
    path: &Path,
    components: &[ComponentInfo],
    modules: &[ModuleInfo],
) -> io::Result<()> {
    let mut file = fs::File::create(path)?;

    writeln!(file, "filepath|summary|public_api|dependencies")?;

    // Components first
    for comp in components {
        let api = comp.public_api.join(", ");
        let deps: Vec<&str> = comp.dependencies.iter().map(|s| s.as_str()).collect();
        let deps_str = deps.join(", ");
        writeln!(
            file,
            "{}|{}|{}|{}",
            comp.filepath,
            escape_csv(&comp.summary),
            api,
            deps_str
        )?;
    }

    // Then individual modules
    for module in modules {
        let deps: Vec<&str> = module.dependencies.iter().map(|s| s.as_str()).collect();
        let deps_str = deps.join(", ");
        writeln!(
            file,
            "{}|{}||{}",
            module.filepath,
            escape_csv(&module.summary),
            deps_str
        )?;
    }

    Ok(())
}

fn pathdiff(path: &Path, base: &Path) -> String {
    path.strip_prefix(base)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| path.to_string_lossy().to_string())
}
