import sqlite3
import os
from datetime import date, datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.graphics import Color, RoundedRectangle

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView


Window.clearcolor = get_color_from_hex("#101820")


class LearningTracker(App):
    def build(self):
        self.title = "Universal Learning Tracker"
        self.db = sqlite3.connect(os.path.join(self.user_data_dir, "learning_tracker.db"))
        self.create_database()

        self.timer_event = None
        self.timer_remaining = 0
        self.timer_total = 0
        self.timer_running = False
        self.timer_subject_id = None
        self.timer_saved = False

        self.main = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8)
        )
        self.show_dashboard()
        return self.main

    # ---------- DATABASE ----------

    def create_database(self):
        cur = self.db.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                goal TEXT,
                progress INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                task_name TEXT,
                completed INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                minutes INTEGER,
                study_date TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_goal (
                id INTEGER PRIMARY KEY,
                minutes INTEGER DEFAULT 120
            )
        """)
        cur.execute("""
            INSERT OR IGNORE INTO daily_goal (id, minutes) VALUES (1, 120)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                title TEXT,
                content TEXT,
                created_at TEXT
            )
        """)
        self.db.commit()

    # ---------- UI HELPERS ----------

    def label(self, text, size=15, color="#FFFFFF", height=35,
              halign="left"):
        lbl = Label(
            text=text,
            font_size=sp(size),
            color=get_color_from_hex(color),
            halign=halign,
            valign="middle",
            size_hint_y=None,
            height=dp(height)
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        return lbl

    def button(self, text, callback, color="#243947", height=46):
        btn = Button(
            text=text,
            size_hint_y=None,
            height=dp(height),
            background_normal="",
            background_color=get_color_from_hex(color),
            color=(1, 1, 1, 1),
            font_size=sp(14)
        )
        if callback:
            btn.bind(on_release=callback)
        return btn

    def panel(self, orientation="vertical", height=None, padding=10, spacing=5):
        box = BoxLayout(
            orientation=orientation,
            padding=dp(padding),
            spacing=dp(spacing),
            size_hint_y=None
        )
        if height:
            box.height = dp(height)
        with box.canvas.before:
            Color(*get_color_from_hex("#1D303D"))
            box.bg = RoundedRectangle(pos=box.pos, size=box.size,
                                      radius=[dp(13)])
        box.bind(pos=self.update_bg, size=self.update_bg)
        return box

    def update_bg(self, widget, value):
        widget.bg.pos = widget.pos
        widget.bg.size = widget.size

    def scroll_content(self):
        scroll = ScrollView()
        content = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        return scroll, content

    def popup(self, title, content, size=(0.9, 0.65)):
        p = Popup(title=title, content=content, size_hint=size)
        p.open()
        return p

    # ---------- STUDY DATA ----------

    def total_minutes(self):
        cur = self.db.cursor()
        cur.execute("SELECT COALESCE(SUM(minutes),0) FROM study_sessions")
        return cur.fetchone()[0]

    def today_minutes(self):
        cur = self.db.cursor()
        cur.execute("SELECT COALESCE(SUM(minutes),0) FROM study_sessions WHERE study_date=?",
                    (date.today().isoformat(),))
        return cur.fetchone()[0]

    def weekly_minutes(self):
        start = (date.today() - timedelta(days=6)).isoformat()
        cur = self.db.cursor()
        cur.execute("SELECT COALESCE(SUM(minutes),0) FROM study_sessions WHERE study_date>=?",
                    (start,))
        return cur.fetchone()[0]

    def weekly_sessions(self):
        start = (date.today() - timedelta(days=6)).isoformat()
        cur = self.db.cursor()
        cur.execute("SELECT COUNT(*) FROM study_sessions WHERE study_date>=?",
                    (start,))
        return cur.fetchone()[0]

    def daily_goal(self):
        cur = self.db.cursor()
        cur.execute("SELECT minutes FROM daily_goal WHERE id=1")
        row = cur.fetchone()
        return row[0] if row else 120

    def streak(self):
        cur = self.db.cursor()
        cur.execute("SELECT DISTINCT study_date FROM study_sessions WHERE minutes>0")
        studied = {date.fromisoformat(r[0]) for r in cur.fetchall()}
        if not studied:
            return 0
        today = date.today()
        if today in studied:
            day = today
        elif today - timedelta(days=1) in studied:
            day = today - timedelta(days=1)
        else:
            return 0
        count = 0
        while day in studied:
            count += 1
            day -= timedelta(days=1)
        return count

    def task_progress(self, subject_id):
        cur = self.db.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(completed),0) FROM tasks WHERE subject_id=?",
                    (subject_id,))
        total, done = cur.fetchone()
        if total:
            return round(done * 100 / total)
        cur.execute("SELECT progress FROM subjects WHERE id=?", (subject_id,))
        row = cur.fetchone()
        return row[0] if row else 0

    def refresh_subject_progress(self, subject_id):
        cur = self.db.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(completed),0) FROM tasks WHERE subject_id=?",
                    (subject_id,))
        total, done = cur.fetchone()
        if total:
            value = round(done * 100 / total)
            cur.execute("UPDATE subjects SET progress=? WHERE id=?", (value, subject_id))
            self.db.commit()
            return value
        cur.execute("SELECT progress FROM subjects WHERE id=?", (subject_id,))
        row = cur.fetchone()
        return row[0] if row else 0

    # ---------- DASHBOARD ----------

    def show_dashboard(self):
        self.main.clear_widgets()
        header = BoxLayout(orientation="vertical", size_hint_y=None,
                          height=dp(76), spacing=dp(1))
        header.add_widget(self.label("UNIVERSAL LEARNING TRACKER",
                                    19, "#63D6B0", 42, "center"))
        header.add_widget(self.label("Build knowledge. Stay consistent.",
                                    13, "#AAB8C2", 28, "center"))
        self.main.add_widget(header)

        cur = self.db.cursor()
        cur.execute("SELECT COUNT(*) FROM subjects")
        subjects = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tasks WHERE completed=1")
        tasks_done = cur.fetchone()[0]
        total = self.total_minutes()
        stats = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                           height=dp(138))
        stats.add_widget(self.stat_card(str(subjects), "Subjects"))
        stats.add_widget(self.stat_card(str(tasks_done), "Tasks completed"))
        stats.add_widget(self.stat_card(f"{total//60}h {total%60}m",
                                       "Total study time"))
        stats.add_widget(self.stat_card(f"🔥 {self.streak()}",
                                       "Day streak"))
        self.main.add_widget(stats)

        goal = self.daily_goal()
        today = self.today_minutes()
        goalbox = self.panel(height=92, padding=9)
        goalbox.add_widget(self.label(f"TODAY: {today} / {goal} minutes",
                                     14, "#63D6B0", 28))
        bar = ProgressBar(max=max(goal, 1), value=min(today, goal),
                          size_hint_y=None, height=dp(13))
        goalbox.add_widget(bar)
        pct = min(round(today * 100 / max(goal, 1)), 100)
        goalbox.add_widget(self.label(f"{pct}% of daily goal", 12,
                                     "#C3D0D8", 24))
        self.main.add_widget(goalbox)

        self.main.add_widget(self.label("MY LEARNING", 17, "#63D6B0", 30))
        scroll, content = self.scroll_content()
        cur.execute("SELECT id,name,category,goal,progress FROM subjects ORDER BY id DESC")
        rows = cur.fetchall()
        if not rows:
            content.add_widget(self.label("No subjects yet. Add your first subject below.",
                                          14, "#AAB8C2", 70, "center"))
        for sid, name, category, goaltext, stored_progress in rows:
            progress = self.refresh_subject_progress(sid)
            card = self.panel(height=158, padding=9, spacing=4)
            card.add_widget(self.label(name, 16, "#FFFFFF", 27))
            card.add_widget(self.label(category or "General", 12,
                                      "#63D6B0", 22))
            card.add_widget(self.label(f"Progress: {progress}%", 12,
                                      "#C3D0D8", 22))
            card.add_widget(ProgressBar(max=100, value=progress,
                                       size_hint_y=None, height=dp(10)))
            actions = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(5))
            actions.add_widget(self.button("Tasks", lambda x, i=sid: self.show_tasks(i),
                                          "#24627B", 36))
            actions.add_widget(self.button("Notes", lambda x, i=sid: self.show_notes(i),
                                          "#7656A8", 36))
            actions.add_widget(self.button("Study", lambda x, i=sid: self.study_timer(i),
                                          "#168C72", 36))
            actions.add_widget(self.button("Delete", lambda x, i=sid: self.delete_subject(i),
                                          "#8A3942", 36))
            card.add_widget(actions)
            content.add_widget(card)
        self.main.add_widget(scroll)

        nav = GridLayout(cols=3, spacing=dp(5), size_hint_y=None, height=dp(48))
        nav.add_widget(self.button("+ Subject", self.add_subject, "#168C72", 44))
        nav.add_widget(self.button("Calendar", self.show_calendar, "#24627B", 44))
        nav.add_widget(self.button("Analytics", self.show_analytics, "#7656A8", 44))
        self.main.add_widget(nav)
        bottom = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(44))
        bottom.add_widget(self.button("Achievements", self.show_achievements,
                                     "#D08B37", 42))
        bottom.add_widget(self.button("Daily Goal", self.set_daily_goal,
                                     "#243947", 42))
        self.main.add_widget(bottom)

    def stat_card(self, number, desc):
        card = BoxLayout(orientation="vertical", padding=dp(7), spacing=dp(2))
        with card.canvas.before:
            Color(*get_color_from_hex("#1D303D"))
            card.bg = RoundedRectangle(pos=card.pos, size=card.size,
                                      radius=[dp(14)])
        card.bind(pos=self.update_bg, size=self.update_bg)
        numsize = 20 if len(number) < 8 else 16
        n = Label(text=number, font_size=sp(numsize),
                  color=get_color_from_hex("#63D6B0"),
                  halign="center", valign="middle", size_hint_y=0.55)
        n.bind(size=lambda w, s: setattr(w, "text_size", s))
        d = Label(text=desc, font_size=sp(12),
                  color=get_color_from_hex("#C3D0D8"),
                  halign="center", valign="middle", size_hint_y=0.45)
        d.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(n)
        card.add_widget(d)
        return card

    # ---------- SUBJECT MANAGEMENT ----------

    def add_subject(self, instance):
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        name = TextInput(hint_text="Subject or skill name", multiline=False,
                        size_hint_y=None, height=dp(44))
        category = TextInput(hint_text="Category (optional)", multiline=False,
                            size_hint_y=None, height=dp(44))
        goal = TextInput(hint_text="Learning goal (optional)", multiline=False,
                        size_hint_y=None, height=dp(44))
        layout.add_widget(name)
        layout.add_widget(category)
        layout.add_widget(goal)
        pop = self.popup("Add Subject", layout, (0.9, 0.58))

        def save(_):
            if not name.text.strip():
                name.hint_text = "Please enter a subject name"
                return
            cur = self.db.cursor()
            cur.execute("INSERT INTO subjects(name,category,goal) VALUES(?,?,?)",
                        (name.text.strip(), category.text.strip() or "General",
                         goal.text.strip()))
            self.db.commit()
            pop.dismiss()
            self.show_dashboard()
        layout.add_widget(self.button("Save Subject", save, "#168C72"))

    def delete_subject(self, subject_id):
        layout = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        layout.add_widget(self.label("Delete this subject, tasks, notes and study records?",
                                     14, "#FFFFFF", 55))
        pop = self.popup("Confirm Delete", layout, (0.88, 0.38))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(self.button("Cancel", lambda x: pop.dismiss()))
        def confirm(_):
            cur = self.db.cursor()
            cur.execute("DELETE FROM tasks WHERE subject_id=?", (subject_id,))
            cur.execute("DELETE FROM notes WHERE subject_id=?", (subject_id,))
            cur.execute("DELETE FROM study_sessions WHERE subject_id=?", (subject_id,))
            cur.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
            self.db.commit()
            pop.dismiss()
            self.show_dashboard()
        row.add_widget(self.button("Delete", confirm, "#8A3942"))
        layout.add_widget(row)

    # ---------- TASKS ----------

    def show_tasks(self, subject_id):
        self.main.clear_widgets()
        cur = self.db.cursor()
        cur.execute("SELECT name,category,goal FROM subjects WHERE id=?", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            self.show_dashboard()
            return
        name, category, goal = subject
        progress = self.refresh_subject_progress(subject_id)
        self.main.add_widget(self.label(name.upper(), 20, "#63D6B0", 38, "center"))
        self.main.add_widget(self.label(category, 13, "#AAB8C2", 28, "center"))
        self.main.add_widget(self.label("Goal: " + (goal or "Not set"), 13, "#FFFFFF", 32))
        self.main.add_widget(self.label(f"Task-based progress: {progress}%", 14,
                                       "#63D6B0", 30))
        self.main.add_widget(ProgressBar(max=100, value=progress,
                                         size_hint_y=None, height=dp(12)))
        scroll, content = self.scroll_content()
        cur.execute("SELECT id,task_name,completed FROM tasks WHERE subject_id=? ORDER BY id",
                    (subject_id,))
        tasks = cur.fetchall()
        if not tasks:
            content.add_widget(self.label("No tasks yet. Add lessons or milestones.",
                                         14, "#AAB8C2", 60, "center"))
        for tid, text, done in tasks:
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(5))
            row.add_widget(self.label(("✓ " if done else "○ ") + text,
                                     13, "#63D6B0" if done else "#FFFFFF", 42))
            row.add_widget(self.button("Toggle", lambda x, t=tid: self.toggle_task(t, subject_id),
                                      "#24627B", 40))
            row.add_widget(self.button("Delete", lambda x, t=tid: self.delete_task(t, subject_id),
                                      "#8A3942", 40))
            content.add_widget(row)
        self.main.add_widget(scroll)
        self.main.add_widget(self.button("+ Add Task", lambda x: self.add_task(subject_id),
                                         "#168C72"))
        self.main.add_widget(self.button("Subject Notes", lambda x: self.show_notes(subject_id),
                                         "#7656A8"))
        self.main.add_widget(self.button("Study Timer", lambda x: self.study_timer(subject_id),
                                         "#24627B"))
        self.main.add_widget(self.button("Back to Dashboard", lambda x: self.show_dashboard()))

    def add_task(self, subject_id):
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        inp = TextInput(hint_text="Lesson, task, or milestone", multiline=False,
                       size_hint_y=None, height=dp(46))
        layout.add_widget(inp)
        pop = self.popup("Add Learning Task", layout, (0.9, 0.35))
        def save(_):
            if not inp.text.strip():
                return
            cur = self.db.cursor()
            cur.execute("INSERT INTO tasks(subject_id,task_name) VALUES(?,?)",
                        (subject_id, inp.text.strip()))
            self.db.commit()
            pop.dismiss()
            self.show_tasks(subject_id)
        layout.add_widget(self.button("Save Task", save, "#168C72"))

    def toggle_task(self, task_id, subject_id):
        cur = self.db.cursor()
        cur.execute("SELECT completed FROM tasks WHERE id=?", (task_id,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE tasks SET completed=? WHERE id=?",
                        (0 if row[0] else 1, task_id))
            self.db.commit()
        self.refresh_subject_progress(subject_id)
        self.show_tasks(subject_id)

    def delete_task(self, task_id, subject_id):
        cur = self.db.cursor()
        cur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.db.commit()
        self.refresh_subject_progress(subject_id)
        self.show_tasks(subject_id)

    # ---------- NOTES ----------

    def show_notes(self, subject_id):
        self.main.clear_widgets()
        cur = self.db.cursor()
        cur.execute("SELECT name FROM subjects WHERE id=?", (subject_id,))
        row = cur.fetchone()
        if not row:
            self.show_dashboard()
            return
        self.main.add_widget(self.label("NOTES • " + row[0], 18,
                                       "#63D6B0", 42, "center"))
        scroll, content = self.scroll_content()
        cur.execute("SELECT id,title,content,created_at FROM notes WHERE subject_id=? ORDER BY id DESC",
                    (subject_id,))
        notes = cur.fetchall()
        if not notes:
            content.add_widget(self.label("No notes saved for this subject yet.",
                                          14, "#AAB8C2", 60, "center"))
        for nid, title, text, created in notes:
            card = self.panel(height=110, padding=8)
            card.add_widget(self.label(title or "Untitled note", 15,
                                      "#FFFFFF", 26))
            preview = text[:110].replace("\n", " ")
            if len(text) > 110:
                preview += "..."
            card.add_widget(self.label(preview, 12, "#C3D0D8", 34))
            card.add_widget(self.label(created, 11, "#AAB8C2", 20))
            actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
            actions.add_widget(self.button("Open/Edit", lambda x, n=nid: self.edit_note(subject_id, n),
                                          "#24627B", 32))
            actions.add_widget(self.button("Delete", lambda x, n=nid: self.delete_note(subject_id, n),
                                          "#8A3942", 32))
            card.add_widget(actions)
            content.add_widget(card)
        self.main.add_widget(scroll)
        self.main.add_widget(self.button("+ New Note", lambda x: self.edit_note(subject_id),
                                         "#168C72"))
        self.main.add_widget(self.button("Back to Subject Tasks",
                                         lambda x: self.show_tasks(subject_id)))

    def edit_note(self, subject_id, note_id=None):
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        title_in = TextInput(hint_text="Note title", multiline=False,
                            size_hint_y=None, height=dp(44))
        body_in = TextInput(hint_text="Write your notes here...",
                            multiline=True)
        layout.add_widget(title_in)
        layout.add_widget(body_in)
        if note_id:
            cur = self.db.cursor()
            cur.execute("SELECT title,content FROM notes WHERE id=?", (note_id,))
            existing = cur.fetchone()
            if existing:
                title_in.text = existing[0] or ""
                body_in.text = existing[1] or ""
        pop = self.popup("Note Editor", layout, (0.94, 0.78))
        def save(_):
            if not title_in.text.strip() and not body_in.text.strip():
                return
            cur = self.db.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            if note_id:
                cur.execute("UPDATE notes SET title=?,content=? WHERE id=?",
                            (title_in.text.strip() or "Untitled note",
                             body_in.text, note_id))
            else:
                cur.execute("INSERT INTO notes(subject_id,title,content,created_at) VALUES(?,?,?,?)",
                            (subject_id, title_in.text.strip() or "Untitled note",
                             body_in.text, now))
            self.db.commit()
            pop.dismiss()
            self.show_notes(subject_id)
        layout.add_widget(self.button("Save Note", save, "#168C72"))

    def delete_note(self, subject_id, note_id):
        cur = self.db.cursor()
        cur.execute("DELETE FROM notes WHERE id=?", (note_id,))
        self.db.commit()
        self.show_notes(subject_id)

    # ---------- STUDY TIMER ----------

    def study_timer(self, subject_id):
        self.main.clear_widgets()
        cur = self.db.cursor()
        cur.execute("SELECT name FROM subjects WHERE id=?", (subject_id,))
        result = cur.fetchone()
        subject_name = result[0] if result else "Study Session"

        self.timer_subject_id = subject_id
        self.timer_running = False
        self.timer_remaining = 0
        self.timer_total = 0
        self.timer_saved = False

        self.main.add_widget(self.label("FOCUS TIMER", 21, "#63D6B0", 40, "center"))
        self.main.add_widget(self.label(subject_name, 15, "#C3D0D8", 32, "center"))
        self.timer_display = Label(text="00:00", font_size=sp(46),
                                   color=get_color_from_hex("#63D6B0"),
                                   halign="center", valign="middle",
                                   size_hint_y=None, height=dp(95))
        self.main.add_widget(self.timer_display)
        self.timer_status = self.label("Select a session length", 13,
                                       "#AAB8C2", 32, "center")
        self.main.add_widget(self.timer_status)

        preset_row = GridLayout(cols=3, spacing=dp(6), size_hint_y=None,
                               height=dp(48))
        for minutes in (25, 45, 60):
            preset_row.add_widget(self.button(f"{minutes} min",
                lambda x, m=minutes: self.set_timer(m), "#24627B", 44))
        self.main.add_widget(preset_row)
        self.custom = TextInput(hint_text="Custom minutes", multiline=False,
                               input_filter="int", size_hint_y=None, height=dp(44))
        self.main.add_widget(self.custom)
        self.main.add_widget(self.button("Set Custom", self.set_custom_timer,
                                         "#243947"))
        self.main.add_widget(self.button("▶ Start", self.start_timer, "#168C72"))
        self.main.add_widget(self.button("Pause / Resume", self.pause_timer,
                                         "#24627B"))
        self.main.add_widget(self.button("Finish & Save", self.finish_timer,
                                         "#D08B37"))
        self.main.add_widget(self.button("Back to Tasks",
                                         lambda x: self.show_tasks(subject_id)))

    def set_timer(self, minutes):
        if self.timer_running:
            self.pause_timer(None)
        self.timer_total = minutes * 60
        self.timer_remaining = self.timer_total
        self.timer_saved = False
        self.update_timer_label()
        self.timer_status.text = f"{minutes} minutes selected"

    def set_custom_timer(self, instance):
        if not self.custom.text:
            self.timer_status.text = "Enter minutes first"
            return
        m = int(self.custom.text)
        if m <= 0:
            self.timer_status.text = "Choose a value above zero"
            return
        self.set_timer(m)

    def start_timer(self, instance):
        if self.timer_remaining <= 0:
            if self.custom.text:
                self.set_custom_timer(None)
            if self.timer_remaining <= 0:
                self.timer_status.text = "Select a duration first"
                return
        if self.timer_running:
            return
        self.timer_running = True
        self.timer_status.text = "Focus mode: keep going!"
        self.timer_event = Clock.schedule_interval(self.tick, 1)

    def tick(self, dt):
        if not self.timer_running:
            return
        self.timer_remaining -= 1
        self.update_timer_label()
        if self.timer_remaining <= 0:
            self.timer_remaining = 0
            self.timer_running = False
            if self.timer_event:
                self.timer_event.cancel()
                self.timer_event = None
            self.timer_status.text = "Time is up!"
            self.save_session(self.timer_total // 60)
            self.timer_saved = True
            self.timer_complete_popup()
            return False

    def pause_timer(self, instance):
        if self.timer_running:
            self.timer_running = False
            if self.timer_event:
                self.timer_event.cancel()
                self.timer_event = None
            self.timer_status.text = "Paused"
        elif self.timer_remaining > 0:
            self.start_timer(None)
        else:
            self.timer_status.text = "Set a timer first"

    def update_timer_label(self):
        m = self.timer_remaining // 60
        s = self.timer_remaining % 60
        self.timer_display.text = f"{m:02d}:{s:02d}"

    def finish_timer(self, instance):
        if self.timer_running:
            self.timer_running = False
            if self.timer_event:
                self.timer_event.cancel()
                self.timer_event = None
        elapsed = self.timer_total - self.timer_remaining
        mins = elapsed // 60
        if mins < 1:
            self.timer_status.text = "Study for at least 1 minute before saving"
            return
        if not self.timer_saved:
            self.save_session(mins)
            self.timer_saved = True
        self.timer_display.text = "Saved"
        self.timer_status.text = f"{mins} minutes recorded"
        self.timer_complete_popup()

    def save_session(self, minutes):
        if minutes <= 0:
            return
        cur = self.db.cursor()
        cur.execute("INSERT INTO study_sessions(subject_id,minutes,study_date) VALUES(?,?,?)",
                    (self.timer_subject_id, minutes, date.today().isoformat()))
        self.db.commit()

    def timer_complete_popup(self):
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        layout.add_widget(self.label("Study session saved. Great work!", 14,
                                    "#63D6B0", 45, "center"))
        pop = self.popup("Session Complete", layout, (0.86, 0.34))
        layout.add_widget(self.button("Dashboard",
                                     lambda x: (pop.dismiss(), self.show_dashboard()),
                                     "#168C72"))
        layout.add_widget(self.button("Continue",
                                     lambda x: (pop.dismiss(), self.study_timer(self.timer_subject_id)),
                                     "#24627B"))

    # ---------- CALENDAR / HISTORY ----------

    def show_calendar(self, instance=None):
        self.main.clear_widgets()
        self.main.add_widget(self.label("LEARNING CALENDAR", 20,
                                        "#63D6B0", 42, "center"))
        self.main.add_widget(self.label("Study history • recent 30 days",
                                        13, "#AAB8C2", 30, "center"))
        scroll, content = self.scroll_content()
        cur = self.db.cursor()
        start = date.today() - timedelta(days=29)
        cur.execute("""
            SELECT study_date, SUM(minutes), COUNT(*)
            FROM study_sessions
            WHERE study_date>=?
            GROUP BY study_date
            ORDER BY study_date DESC
        """, (start.isoformat(),))
        records = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        for offset in range(30):
            day = date.today() - timedelta(days=offset)
            key = day.isoformat()
            minutes, sessions = records.get(key, (0, 0))
            row = self.panel(orientation="horizontal", height=54, padding=7, spacing=5)
            row.add_widget(self.label(day.strftime("%a, %d %b"), 13,
                                     "#FFFFFF", 38))
            if minutes:
                row.add_widget(self.label(f"{minutes} min • {sessions} session(s)",
                                         12, "#63D6B0", 38, "right"))
            else:
                row.add_widget(self.label("No study recorded", 12,
                                         "#7D8C96", 38, "right"))
            content.add_widget(row)
        self.main.add_widget(scroll)
        self.main.add_widget(self.button("Back to Dashboard",
                                         lambda x: self.show_dashboard()))

    # ---------- WEEKLY ANALYTICS ----------

    def show_analytics(self, instance=None):
        self.main.clear_widgets()
        self.main.add_widget(self.label("WEEKLY ANALYTICS", 20,
                                        "#63D6B0", 42, "center"))
        minutes = self.weekly_minutes()
        sessions = self.weekly_sessions()
        cur = self.db.cursor()
        start = (date.today() - timedelta(days=6)).isoformat()
        cur.execute("SELECT COUNT(*) FROM tasks WHERE completed=1")
        all_done = cur.fetchone()[0]
        cur.execute("""
            SELECT s.name, COALESCE(SUM(ss.minutes),0)
            FROM subjects s LEFT JOIN study_sessions ss ON ss.subject_id=s.id
            AND ss.study_date>=?
            GROUP BY s.id ORDER BY 2 DESC
        """, (start,))
        per_subject = cur.fetchall()

        stats = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                           height=dp(120))
        stats.add_widget(self.stat_card(f"{minutes//60}h {minutes%60}m",
                                       "Last 7 days"))
        stats.add_widget(self.stat_card(str(sessions), "Sessions this week"))
        self.main.add_widget(stats)
        self.main.add_widget(self.label("Study time by subject (7 days)",
                                        15, "#63D6B0", 35))
        scroll, content = self.scroll_content()
        if not per_subject:
            content.add_widget(self.label("No subjects yet.", 13,
                                          "#AAB8C2", 45))
        for name, mins in per_subject:
            row = self.panel(height=55, padding=8, spacing=4)
            row.add_widget(self.label(name, 13, "#FFFFFF", 22))
            row.add_widget(self.label(f"{mins} minutes", 12,
                                     "#63D6B0", 22))
            content.add_widget(row)
        self.main.add_widget(scroll)
        self.main.add_widget(self.label(f"Tasks completed overall: {all_done}",
                                        13, "#C3D0D8", 32))
        self.main.add_widget(self.button("Back to Dashboard",
                                         lambda x: self.show_dashboard()))

    # ---------- ACHIEVEMENTS ----------

    def show_achievements(self, instance=None):
        self.main.clear_widgets()
        self.main.add_widget(self.label("ACHIEVEMENTS", 20,
                                        "#63D6B0", 42, "center"))
        total = self.total_minutes()
        streak = self.streak()
        cur = self.db.cursor()
        cur.execute("SELECT COUNT(*) FROM tasks WHERE completed=1")
        tasks = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM subjects")
        subjects = cur.fetchone()[0]

        milestones = [
            ("First Steps", "Add your first learning subject", subjects >= 1),
            ("Task Starter", "Complete your first task", tasks >= 1),
            ("Focused Learner", "Study for 1 total hour", total >= 60),
            ("Dedicated", "Study for 5 total hours", total >= 300),
            ("Knowledge Builder", "Study for 10 total hours", total >= 600),
            ("Consistency", "Reach a 3-day study streak", streak >= 3),
            ("Habit Maker", "Reach a 7-day study streak", streak >= 7),
            ("Task Champion", "Complete 25 tasks", tasks >= 25),
            ("Subject Explorer", "Add 5 subjects", subjects >= 5),
        ]
        scroll, content = self.scroll_content()
        for title, detail, unlocked in milestones:
            card = self.panel(height=70, padding=8)
            card.add_widget(self.label(("🏆 " if unlocked else "🔒 ") + title,
                                      14, "#63D6B0" if unlocked else "#AAB8C2", 28))
            card.add_widget(self.label(detail, 12, "#C3D0D8", 26))
            content.add_widget(card)
        self.main.add_widget(scroll)
        self.main.add_widget(self.button("Back to Dashboard",
                                         lambda x: self.show_dashboard()))

    # ---------- DAILY GOAL ----------

    def set_daily_goal(self, instance):
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        inp = TextInput(text=str(self.daily_goal()), hint_text="Minutes per day",
                        input_filter="int", multiline=False,
                        size_hint_y=None, height=dp(44))
        layout.add_widget(self.label("Daily target (minutes)", 13))
        layout.add_widget(inp)
        pop = self.popup("Set Daily Goal", layout, (0.88, 0.38))
        def save(_):
            if not inp.text:
                return
            value = int(inp.text)
            if value < 1:
                return
            cur = self.db.cursor()
            cur.execute("UPDATE daily_goal SET minutes=? WHERE id=1", (value,))
            self.db.commit()
            pop.dismiss()
            self.show_dashboard()
        layout.add_widget(self.button("Save Goal", save, "#168C72"))

    # ---------- CLEAN EXIT ----------

    def on_stop(self):
        if self.timer_event:
            self.timer_event.cancel()
        self.db.close()


LearningTracker().run()
