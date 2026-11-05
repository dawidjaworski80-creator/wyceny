import tkinter as tk

from app import CncQuotesApp, DataStore, run_splash_screen


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    try:
        from excel_templates import prewarm_excel

        prewarm_excel()
    except ImportError:
        pass
    run_splash_screen(root, DataStore().load_settings())
    app = CncQuotesApp(root)
    if not app.prompt_login():
        root.destroy()
        raise SystemExit
    root.deiconify()
    root.mainloop()
