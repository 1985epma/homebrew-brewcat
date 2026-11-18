//! The Skills and MCP tabs: drawing, and the actions their buttons start. The rules (confirmation texts, jobs,
//! validation) are in `extras.rs`.

use std::path::PathBuf;

use eframe::egui::{self, Align, Layout, RichText, TextStyle};
use egui_extras::{Column, TableBuilder};

use crate::brewrunner::Tag;
use crate::extras_core::{MCP_PRESETS, SKILL_PRESETS, Scope, TARGETS};
use crate::gui::app::BrewcatApp;
use crate::gui::dialogs::{Dialog, Then};
use crate::gui::extras::{McpIssue, SkillPlan, TargetBar};
use crate::gui::worker::{self, Msg};

type Chosen = (Vec<&'static str>, Scope, Option<PathBuf>);

/// The tools and scope to install into. Without a tool there is nothing to do; with Project scope and no folder
/// yet, ask for one. `Err(None)` means the user backed out.
fn resolve(bar: &mut TargetBar) -> Result<Chosen, Option<Box<Dialog>>> {
    if bar.targets().is_empty() {
        return Err(Some(Box::new(Dialog::Info {
            title: "Install".to_string(),
            text: "Select at least one target (Claude, Kiro or VS Code).".to_string(),
        })));
    }
    if bar.needs_project() {
        match rfd::FileDialog::new().set_title("Project folder").pick_folder() {
            Some(folder) => bar.set_project(folder),
            None => return Err(None),
        }
    }
    Ok((bar.targets(), bar.scope, bar.project.clone()))
}

/// "Install to: [x] Claude [ ] Kiro [ ] VS Code | User / Project  Folder…". Returns true when the choice changed.
fn target_bar(ui: &mut egui::Ui, bar: &mut TargetBar) -> bool {
    let mut changed = false;
    egui::Frame::group(ui.style()).show(ui, |ui| {
        ui.horizontal_wrapped(|ui| {
            ui.label(RichText::new("Install to").strong());
            for (i, (_, label)) in TARGETS.iter().enumerate() {
                changed |= ui.checkbox(&mut bar.on[i], *label).changed();
            }
            ui.separator();
            changed |= ui.radio_value(&mut bar.scope, Scope::User, "User (global)").changed();
            changed |= ui.radio_value(&mut bar.scope, Scope::Project, "Project").changed();
            if ui.button("Folder…").clicked()
                && let Some(folder) = rfd::FileDialog::new().set_title("Project folder").pick_folder()
            {
                bar.set_project(folder);
                changed = true;
            }
            ui.label(RichText::new(bar.project_label()).weak());
        });
    });
    changed
}

impl BrewcatApp {
    // ───────────────────────── Skills ─────────────────────────
    pub fn scan_skills(&mut self) {
        let spec = self.skills.source.trim().to_string();
        if spec.is_empty() || self.skills.scanning {
            return;
        }
        self.skills.scanning = true;
        self.log(Tag::Info, &format!("\nScanning skills from {spec} …\n"));
        let n = self.notifier();
        std::thread::spawn(move || n.send(Msg::Scan(worker::scan_source(&spec))));
    }

    /// "Install selected skills": ask first, with the source, warnings and destinations.
    pub fn install_skills(&mut self) {
        let folders: Vec<PathBuf> = self.skills.checked().iter().map(|r| r.folder.clone()).collect();
        if folders.is_empty() {
            self.info("Skills", "Select one or more skills first (scan a source).");
            return;
        }
        let (targets, scope, project) = match resolve(&mut self.skills.bar) {
            Ok(chosen) => chosen,
            Err(Some(dialog)) => return self.push_dialog(*dialog),
            Err(None) => return,
        };
        let plan = SkillPlan { folders, targets, scope, project };
        match self.skills.confirm_text(&plan, &self.home) {
            Ok(text) => self.push_dialog(Dialog::Confirm { title: "Confirm installation".to_string(), text, then: Then::Skills(plan) }),
            Err(e) => self.error("Skills", &e.to_string()),
        }
    }

    pub fn skills_tab(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Source (GitHub repo/URL or local folder):");
            ui.add(egui::TextEdit::singleline(&mut self.skills.source).desired_width(380.0));
            egui::ComboBox::from_id_salt("skill-presets").selected_text("presets").show_ui(ui, |ui| {
                for preset in SKILL_PRESETS {
                    if ui.selectable_label(false, preset).clicked() {
                        self.skills.source = preset.to_string();
                    }
                }
            });
            if ui.button("Browse…").clicked()
                && let Some(folder) = rfd::FileDialog::new().set_title("Folder with skills").pick_folder()
            {
                self.skills.source = folder.to_string_lossy().into_owned();
            }
            if ui.add_enabled(!self.skills.scanning, egui::Button::new(if self.skills.scanning { "Scanning…" } else { "Scan" })).clicked()
            {
                self.scan_skills();
            }
            if ui.button("Select all").clicked() {
                self.skills.select_all(true);
            }
            if ui.button("Select none").clicked() {
                self.skills.select_all(false);
            }
        });
        ui.add_space(6.0);

        let mut bar_changed = false;
        egui::Panel::bottom("skills-bottom").show_separator_line(false).show(ui, |ui| {
            ui.add_space(6.0);
            bar_changed = target_bar(ui, &mut self.skills.bar);
            ui.label(
                RichText::new("C = Claude, K = Kiro, V = VS Code. Shows where each skill is already installed for the selected scope.")
                    .weak(),
            );
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if ui.button("Install selected skills").clicked() {
                    self.install_skills();
                }
            });
        });
        if bar_changed {
            self.skills.refresh_marks(&self.home.clone());
        }

        let rows = &mut self.skills.rows;
        TableBuilder::new(ui)
            .id_salt("skills")
            .striped(true)
            .resizable(true)
            .column(Column::initial(240.0).at_least(100.0).clip(true))
            .column(Column::exact(70.0))
            .column(Column::remainder().at_least(150.0).clip(true))
            .header(24.0, |mut header| {
                for title in ["Skill", "C K V", "Description"] {
                    header.col(|ui| {
                        ui.strong(title);
                    });
                }
            })
            .body(|body| {
                body.rows(24.0, rows.len(), |mut row| {
                    let r = &mut rows[row.index()];
                    row.col(|ui| {
                        ui.checkbox(&mut r.checked, r.name.clone());
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(&r.marks).monospace());
                    });
                    row.col(|ui| {
                        ui.add(egui::Label::new(&r.desc).truncate());
                    });
                });
            });
    }

    // ───────────────────────── MCP ─────────────────────────
    /// "Install MCP server": validate, then ask first (with a warning for a custom command).
    pub fn install_mcp(&mut self) {
        if self.mcp.form.name.trim().is_empty() || self.mcp.form.command.trim().is_empty() {
            self.info("MCP", "Pick a server or fill in name and command.");
            return;
        }
        let (targets, scope, project) = match resolve(&mut self.mcp.bar) {
            Ok(chosen) => chosen,
            Err(Some(dialog)) => return self.push_dialog(*dialog),
            Err(None) => return,
        };
        let plan = match self.mcp.prepare(targets, scope, project) {
            Ok(plan) => plan,
            Err(McpIssue::MissingNameOrCommand) => return self.info("MCP", "Pick a server or fill in name and command."),
            Err(McpIssue::InvalidArgs) => return self.error("MCP", "Invalid arguments: No closing quotation"),
        };
        match plan.confirm_text(&self.home) {
            Ok(text) => {
                self.push_dialog(Dialog::Confirm { title: "Confirm installation".to_string(), text, then: Then::Mcp(Box::new(plan)) })
            }
            Err(e) => self.error("MCP", &e.to_string()),
        }
    }

    pub fn mcp_tab(&mut self, ui: &mut egui::Ui) {
        let mut picked: Option<usize> = None;
        let selected = self.mcp.selected;
        {
            let marks = &self.mcp.marks;
            ui.push_id("mcp-presets", |ui| {
                TableBuilder::new(ui)
                    .striped(true)
                    .resizable(true)
                    .sense(egui::Sense::click())
                    .max_scroll_height(210.0)
                    .column(Column::initial(170.0).at_least(80.0).clip(true))
                    .column(Column::exact(70.0))
                    .column(Column::exact(70.0))
                    .column(Column::remainder().at_least(150.0).clip(true))
                    .header(24.0, |mut header| {
                        for title in ["Server", "Command", "C K V", "Description"] {
                            header.col(|ui| {
                                ui.strong(title);
                            });
                        }
                    })
                    .body(|body| {
                        body.rows(24.0, MCP_PRESETS.len(), |mut row| {
                            let i = row.index();
                            let p = &MCP_PRESETS[i];
                            row.set_selected(selected == Some(i));
                            row.col(|ui| {
                                ui.label(p.name);
                            });
                            row.col(|ui| {
                                ui.label(p.command);
                            });
                            row.col(|ui| {
                                ui.label(RichText::new(marks.get(i).map(String::as_str).unwrap_or("· · ·")).monospace());
                            });
                            row.col(|ui| {
                                ui.add(egui::Label::new(p.desc).truncate());
                            });
                            if row.response().clicked() {
                                picked = Some(i);
                            }
                        });
                    });
            });
        }
        if let Some(i) = picked {
            self.mcp.pick_preset(i);
        }

        ui.add_space(8.0);
        egui::Frame::group(ui.style()).show(ui, |ui| {
            ui.label(RichText::new("Server definition (edit freely or type your own)").strong());
            egui::Grid::new("mcp-form").num_columns(2).spacing([8.0, 4.0]).show(ui, |ui| {
                let form = &mut self.mcp.form;
                for (label, value) in [
                    ("Name", &mut form.name),
                    ("Command", &mut form.command),
                    ("Arguments", &mut form.args),
                    ("Env (KEY=VALUE, comma-separated)", &mut form.env),
                ] {
                    ui.label(label);
                    ui.add(egui::TextEdit::singleline(value).desired_width(f32::INFINITY).font(TextStyle::Monospace));
                    ui.end_row();
                }
            });
        });
        ui.add_space(8.0);
        if target_bar(ui, &mut self.mcp.bar) {
            self.mcp.refresh_marks(&self.home.clone());
        }
        ui.label(
            RichText::new("Edits the MCP config of each target (a .bak copy is kept). Needs node (npx) or uv (uvx) installed — get them in the Packages tab.")
                .weak(),
        );
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            if ui.button("Install MCP server").clicked() {
                self.install_mcp();
            }
        });
    }
}
