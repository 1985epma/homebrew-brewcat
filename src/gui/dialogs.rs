//! Modal dialogs. egui is immediate-mode, so a question is a value in a queue (`Dialog`); the window shows the first
//! one every frame and acts on the answer. Nothing in the app blocks waiting for a click, so tests can answer
//! dialogs directly.

use std::path::PathBuf;

use eframe::egui::{self, Align, Id, Layout, Modal, RichText};

use crate::gui::extras::{McpPlan, SkillPlan};
use crate::gui::state::PROFILES;

/// What happens when a yes/no question is answered.
#[derive(Debug, Clone)]
pub enum Then {
    /// Run these brew commands.
    RunBrew(Vec<Vec<String>>),
    /// Quit although a brew command is running (it is stopped first).
    Quit,
    InstallRosetta,
    /// Install these skills.
    Skills(SkillPlan),
    /// Replace the skill folder that already exists at this path.
    Replace(PathBuf),
    /// Add this MCP server.
    Mcp(Box<McpPlan>),
}

#[derive(Debug, Clone)]
pub enum Dialog {
    /// First-run welcome: `selected` indexes `PROFILES`.
    Welcome {
        selected: usize,
    },
    /// The install plan with Install / Cancel.
    Plan {
        title: String,
        text: String,
        cmds: Vec<Vec<String>>,
    },
    /// A plain yes/no question.
    Confirm {
        title: String,
        text: String,
        then: Then,
    },
    Info {
        title: String,
        text: String,
    },
    Error {
        title: String,
        text: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Answer {
    Yes,
    No,
    /// The welcome was answered: the profile label to show kits for, or None when skipped or closed.
    Start(Option<String>),
}

impl Dialog {
    pub fn title(&self) -> &str {
        match self {
            Dialog::Welcome { .. } => "Welcome to brewcat",
            Dialog::Plan { title, .. } | Dialog::Confirm { title, .. } | Dialog::Info { title, .. } | Dialog::Error { title, .. } => title,
        }
    }

    /// The answer when the dialog is closed with Escape or by clicking outside it.
    pub fn dismissed(&self) -> Answer {
        match self {
            Dialog::Welcome { .. } => Answer::Start(None),
            Dialog::Info { .. } | Dialog::Error { .. } => Answer::Yes,
            _ => Answer::No,
        }
    }
}

fn scrolling_text(ui: &mut egui::Ui, text: &str, width: f32, max_height: f32, monospace: bool) {
    egui::ScrollArea::vertical().max_height(max_height).show(ui, |ui| {
        ui.set_width(width);
        let text = if monospace { RichText::new(text).monospace() } else { RichText::new(text) };
        ui.add(egui::Label::new(text).selectable(true).wrap());
    });
}

fn buttons(ui: &mut egui::Ui, ok: &str, cancel: Option<&str>) -> Option<bool> {
    let mut answer = None;
    ui.add_space(8.0);
    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
        if ui.button(ok).clicked() {
            answer = Some(true);
        }
        if let Some(cancel) = cancel
            && ui.button(cancel).clicked()
        {
            answer = Some(false);
        }
    });
    answer
}

/// Show `dialog` on top of everything. Returns the answer once the user gives one.
pub fn show(ctx: &egui::Context, dialog: &mut Dialog) -> Option<Answer> {
    let dismissed = dialog.dismissed();
    let mut answer: Option<Answer> = None;
    let response = Modal::new(Id::unique("brewcat-dialog")).show(ctx, |ui| {
        match dialog {
            Dialog::Welcome { selected } => {
                ui.set_width(400.0);
                ui.label(RichText::new("Welcome to brewcat").size(20.0).strong());
                ui.add_space(6.0);
                ui.label(
                    "brewcat is a catalog of Homebrew packages: browse, pick what you need and install it in a click. Nothing is installed until you confirm.",
                );
                ui.add_space(8.0);
                ui.label("What do you do?");
                egui::ComboBox::from_id_salt("welcome-profile").width(360.0).selected_text(PROFILES[*selected].0).show_ui(ui, |ui| {
                    for (i, (label, _)) in PROFILES.iter().enumerate() {
                        ui.selectable_value(selected, i, *label);
                    }
                });
                ui.add_space(8.0);
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if ui.button("Show me a starter kit").clicked() {
                        answer = Some(Answer::Start(Some(PROFILES[*selected].0.to_string())));
                    }
                    if ui.button("Skip").clicked() {
                        answer = Some(Answer::Start(None));
                    }
                });
            }
            Dialog::Plan { title, text, .. } => {
                ui.label(RichText::new(title.as_str()).size(17.0).strong());
                ui.add_space(4.0);
                scrolling_text(ui, text, 580.0, 320.0, false);
                if let Some(ok) = buttons(ui, "Install", Some("Cancel")) {
                    answer = Some(if ok { Answer::Yes } else { Answer::No });
                }
            }
            Dialog::Confirm { title, text, .. } => {
                ui.label(RichText::new(title.as_str()).size(17.0).strong());
                ui.add_space(4.0);
                scrolling_text(ui, text, 480.0, 320.0, false);
                if let Some(ok) = buttons(ui, "Yes", Some("No")) {
                    answer = Some(if ok { Answer::Yes } else { Answer::No });
                }
            }
            Dialog::Info { title, text } | Dialog::Error { title, text } => {
                ui.label(RichText::new(title.as_str()).size(17.0).strong());
                ui.add_space(4.0);
                scrolling_text(ui, text, 420.0, 240.0, false);
                if buttons(ui, "OK", None).is_some() {
                    answer = Some(Answer::Yes);
                }
            }
        }
    });
    if answer.is_none() && response.should_close() {
        answer = Some(dismissed);
    }
    answer
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dismissing_a_dialog_is_the_safe_answer() {
        let plan = Dialog::Plan { title: "t".into(), text: "x".into(), cmds: vec![] };
        assert_eq!(plan.dismissed(), Answer::No);
        let confirm = Dialog::Confirm { title: "t".into(), text: "x".into(), then: Then::Quit };
        assert_eq!(confirm.dismissed(), Answer::No);
        assert_eq!(Dialog::Welcome { selected: 0 }.dismissed(), Answer::Start(None));
        assert_eq!(Dialog::Info { title: "t".into(), text: "x".into() }.dismissed(), Answer::Yes);
        assert_eq!(Dialog::Welcome { selected: 0 }.title(), "Welcome to brewcat");
    }
}
