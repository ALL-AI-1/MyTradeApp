import sqlite3
import json
import threading
import time
from functools import partial
from kivy.clock import Clock
from kivy.core.window import Window
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDFloatingActionButton
from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.card import MDCard
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.screen import MDScreen
from kivymd.uix.behaviors import TouchBehavior
from kivymd.uix.snackbar import Snackbar
from kivymd.theming import ThemeManager
from concurrent.futures import ThreadPoolExecutor
import queue

# Set mobile window size
Window.size = (360, 640)

class KivyMDSimpleMobileApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.accent_palette = "Teal"
        
    def build(self):
        self.selected_row = None
        self.data_cache = {}
        self.connection_pool = queue.Queue(maxsize=2)
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # Pagination variables
        self.current_letter = None
        self.current_offset = 0
        self.loaded_rows = []
        self.has_more_data = True
        
        # Initialize database
        self.init_database()
        
        # Create main screen
        screen = MDScreen()
        
        # Main layout
        main_layout = MDBoxLayout(
            orientation="vertical", 
            spacing=5, 
            padding=5,
            size_hint=(1, 1)
        )
        
        # Top App Bar
        self.top_bar = MDTopAppBar(
            title="TradePlus Mobile",
            elevation=1,
            md_bg_color=self.theme_cls.primary_color,
            specific_text_color=(1, 1, 1, 1),
            size_hint_y=None,
            height=48
        )
        main_layout.add_widget(self.top_bar)
        
        # Alphabet Buttons Section
        alphabet_card = MDCard(
            elevation=1,
            radius=[6],
            padding=5,
            md_bg_color=(1, 1, 1, 1),
            size_hint_y=None,
            height=100
        )
        
        alphabet_layout = MDBoxLayout(orientation="vertical", spacing=2)
        
        # Alphabet title
        alphabet_title = MDLabel(
            text="Browse Companies",
            theme_text_color="Primary",
            font_style="Subtitle1",
            size_hint_y=None,
            height=20
        )
        alphabet_layout.add_widget(alphabet_title)
        
        # Alphabet buttons - Vertically scrollable
        self.alphabet_scroll = MDScrollView(
            size_hint=(1, None),
            height=70,
            bar_width=4,
            do_scroll_x=True,
            do_scroll_y=True
        )
        
        self.alphabet_grid = MDGridLayout(
            cols=6,
            spacing=2,
            size_hint=(None, None),
            height=140,  # Double height for vertical scrolling
            adaptive_width=True
        )
        
        for i in range(ord("A"), ord("Z") + 1):
            letter = chr(i)
            btn = MDFlatButton(
                text=letter,
                size_hint=(None, None),
                size=(50, 30),
                theme_text_color="Primary",
                font_size=12
            )
            btn.bind(on_press=lambda instance, l=letter: self.show_data_optimized(l))
            self.alphabet_grid.add_widget(btn)
        
        self.alphabet_scroll.add_widget(self.alphabet_grid)
        alphabet_layout.add_widget(self.alphabet_scroll)
        alphabet_card.add_widget(alphabet_layout)
        main_layout.add_widget(alphabet_card)
        
        # Data Display Section
        data_card = MDCard(
            elevation=1,
            radius=[6],
            padding=5,
            md_bg_color=(1, 1, 1, 1),
            size_hint=(1, 1)
        )
        
        data_layout = MDBoxLayout(orientation="vertical", spacing=2)
        
        # Data title
        self.data_title = MDLabel(
            text="Select a letter to browse",
            theme_text_color="Primary",
            font_style="Subtitle1",
            size_hint_y=None,
            height=20
        )
        data_layout.add_widget(self.data_title)
        
        # Simple list view
        self.list_scroll = MDScrollView(
            size_hint=(1, 1),
            bar_width=6
        )
        
        self.list_layout = MDBoxLayout(
            orientation="vertical",
            spacing=2,
            size_hint=(1, None),
            adaptive_height=True
        )
        
        self.list_scroll.add_widget(self.list_layout)
        data_layout.add_widget(self.list_scroll)
        
        # Load More Button
        self.load_more_btn = MDRaisedButton(
            text="Load More (+20)",
            size_hint_y=None,
            height=32,
            elevation=1,
            md_bg_color=self.theme_cls.accent_color,
            opacity=0,
            font_size=10
        )
        self.load_more_btn.bind(on_press=self.load_more_data)
        data_layout.add_widget(self.load_more_btn)
        
        data_card.add_widget(data_layout)
        main_layout.add_widget(data_card)
        
        # Bottom Action Section
        action_card = MDCard(
            elevation=1,
            radius=[6],
            padding=5,
            md_bg_color=(1, 1, 1, 1),
            size_hint_y=None,
            height=50
        )
        
        action_layout = MDBoxLayout(orientation="horizontal", spacing=5)
        
        # Status label
        self.status_label = MDLabel(
            text="Ready",
            theme_text_color="Secondary",
            font_style="Caption",
            size_hint_x=0.6
        )
        action_layout.add_widget(self.status_label)
        
        # Save FAB
        self.save_fab = MDFloatingActionButton(
            icon="content-save",
            size_hint_x=0.4,
            elevation=1,
            md_bg_color=self.theme_cls.accent_color
        )
        self.save_fab.bind(on_press=self.save_data)
        action_layout.add_widget(self.save_fab)
        
        action_card.add_widget(action_layout)
        main_layout.add_widget(action_card)
        
        screen.add_widget(main_layout)
        return screen

    def init_database(self):
        """Initialize database with mobile optimizations"""
        try:
            for _ in range(2):
                conn = sqlite3.connect("mydata.db", check_same_thread=False)
                cursor = conn.cursor()
                
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_company_lower 
                    ON tradeplus_brands(LOWER(company))
                """)
                
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=33554432")
                cursor.execute("PRAGMA page_size=4096")
                
                conn.commit()
                self.connection_pool.put(conn)
            
            print("Database optimized for mobile")
        except Exception as e:
            print(f"Database optimization failed: {e}")
    
    def get_connection(self):
        """Get connection from pool"""
        try:
            return self.connection_pool.get_nowait()
        except queue.Empty:
            return sqlite3.connect("mydata.db", check_same_thread=False)
    
    def return_connection(self, conn):
        """Return connection to pool"""
        try:
            self.connection_pool.put_nowait(conn)
        except queue.Full:
            conn.close()

    def show_data_optimized(self, letter):
        """Mobile-optimized data loading with pagination"""
        # Reset pagination for new letter
        self.current_letter = letter
        self.current_offset = 0
        self.loaded_rows = []
        self.has_more_data = True
        
        # Check cache first
        if letter in self.data_cache and self.current_offset == 0:
            print(f"Cache hit for {letter}")
            self._render_rows_fast(letter, self.data_cache[letter], None, 0)
            return
        
        self.list_layout.clear_widgets()
        self.selected_row = None
        self.load_more_btn.opacity = 0
        self.data_title.text = f"Companies: '{letter}'"
        self.status_label.text = f"Loading {letter}..."

        # Use threading for database query
        threading.Thread(target=self._load_data_optimized, args=(letter, 0), daemon=True).start()

    def _load_data_optimized(self, letter, offset):
        """Mobile-optimized database query with pagination"""
        start_time = time.time()
        rows = []
        error_msg = None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = f"""
                SELECT accode, company, Name, Address, phone, TAXNO
                FROM tradeplus_brands
                WHERE LOWER(company) LIKE ?
                LIMIT 20 OFFSET ?
            """
            cursor.execute(query, (letter.lower() + "%", offset))
            rows = cursor.fetchall()
            
            self.return_connection(conn)
            
            if offset == 0:
                self.data_cache[letter] = rows
            
            query_time = time.time() - start_time
            print(f"Mobile query time: {query_time:.3f}s, Loaded {len(rows)} rows")
            
        except Exception as e:
            error_msg = str(e)

        Clock.schedule_once(partial(self._render_rows_fast, letter, rows, error_msg, offset), 0)

    def _render_rows_fast(self, letter, rows, error_msg, offset, dt=None):
        """Simple list rendering"""
        start_time = time.time()
        
        if offset == 0:
            self.loaded_rows = []
        
        if error_msg:
            if offset == 0:
                error_label = MDLabel(
                    text=f"Error: {error_msg}",
                    theme_text_color="Error",
                    font_style="Body2",
                    size_hint_y=None,
                    height=40
                )
                self.list_layout.add_widget(error_label)
                self.status_label.text = "Error loading data"
            return

        if not rows:
            if offset == 0:
                no_data_label = MDLabel(
                    text=f"No companies found starting with {letter}",
                    theme_text_color="Secondary",
                    font_style="Body2",
                    size_hint_y=None,
                    height=40
                )
                self.list_layout.add_widget(no_data_label)
                self.status_label.text = "No results"
            else:
                self.has_more_data = False
                self.load_more_btn.opacity = 0
            return

        # Add new rows to existing data
        self.loaded_rows.extend(rows)
        
        # Add simple list items
        for row in rows:
            # Create a simple card for each company - larger with name, address, tax
            company_card = MDCard(
                elevation=1,
                radius=[4],
                padding=12,
                md_bg_color=(0.95, 0.95, 0.95, 1),
                size_hint_y=None,
                height=80  # Larger height
            )
            
            # Company info layout
            info_layout = MDBoxLayout(orientation="vertical", spacing=4)
            
            # Company name - larger text (125%)
            company_label = MDLabel(
                text=row[1] or "N/A",
                theme_text_color="Primary",
                font_style="Subtitle1",  # Larger font style (125%)
                size_hint_y=None,
                height=32  # Larger height for company name
            )
            info_layout.add_widget(company_label)
            
            # Address and TAXNO - normal size
            details_label = MDLabel(
                text=f"{row[3] or 'N/A'} | Tax: {row[5] or 'N/A'}",
                theme_text_color="Secondary",
                font_style="Caption",
                size_hint_y=None,
                height=20
            )
            info_layout.add_widget(details_label)
            
            company_card.add_widget(info_layout)
            
            # Bind click event
            company_card.bind(on_touch_down=lambda instance, touch, r=row: self.on_company_press(r) if instance.collide_point(*touch.pos) else False)
            
            self.list_layout.add_widget(company_card)

        # Update pagination state
        self.current_offset += len(rows)
        self.has_more_data = len(rows) == 20
        
        # Show/hide load more button
        if self.has_more_data:
            self.load_more_btn.opacity = 1
            self.load_more_btn.text = f"Load More (+20) - {len(self.loaded_rows)}"
        else:
            self.load_more_btn.opacity = 0

        render_time = time.time() - start_time
        self.status_label.text = f"{len(self.loaded_rows)} rows in {render_time:.3f}s"

    def on_company_press(self, row):
        """Handle company selection"""
        self.selected_row = {
            "Accode": row[0],
            "Company": row[1],
            "Name": row[2],
            "Address": row[3],
            "Phone": row[4],
            "TAXNO": row[5]
        }
        print("Row selected:", self.selected_row)
        
        # Show selection feedback
        snackbar = Snackbar(
            snackbar_x="10dp",
            snackbar_y="10dp",
            size_hint_x=0.8,
            bg_color=self.theme_cls.accent_color
        )
        snackbar.text = f"Selected: {row[1]}"
        snackbar.open()

    def load_more_data(self, instance):
        """Load 20 more rows"""
        if not self.current_letter or not self.has_more_data:
            return
        
        self.status_label.text = f"Loading more {self.current_letter}..."
        threading.Thread(target=self._load_data_optimized, args=(self.current_letter, self.current_offset), daemon=True).start()

    def save_data(self, instance):
        """Save selected row into JSON"""
        if not self.selected_row:
            snackbar = Snackbar(
                snackbar_x="10dp",
                snackbar_y="10dp",
                size_hint_x=0.8,
                bg_color=(1, 0, 0, 1)
            )
            snackbar.text = "No row selected!"
            snackbar.open()
            return

        self.status_label.text = "Saving..."
        payload = dict(self.selected_row)

        def worker():
            start_time = time.time()
            
            try:
                with open("selected.json", "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4)
                print(f"Row saved to selected.json: {payload}")
                
                total_time = time.time() - start_time
                Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', f"Saved in {total_time:.2f}s"), 0)
                
                # Show success snackbar
                Clock.schedule_once(lambda dt: self.show_success_snackbar(), 0)
                
            except Exception as e:
                print(f"Failed to save JSON: {e}")
                Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', f"Save failed: {e}"), 0)

        self.executor.submit(worker)
    
    def show_success_snackbar(self):
        """Show success snackbar"""
        snackbar = Snackbar(
            snackbar_x="10dp",
            snackbar_y="10dp",
            size_hint_x=0.8,
            bg_color=(0, 0.8, 0, 1)
        )
        snackbar.text = "Data saved successfully!"
        snackbar.open()

if __name__ == "__main__":
    KivyMDSimpleMobileApp().run()
