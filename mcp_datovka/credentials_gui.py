"""Local credential repair: verify identity before replacing stored credentials."""
import json
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config
from .setup import save_config
from .services.isds import verify_sender


@dataclass(frozen=True)
class LoginCandidate:
    alias: str
    box_id: str
    environment: str
    username: str = field(repr=False)
    password: str = field(repr=False)


def verify_and_save(alias, username, password):
    """One identity request. No message lists, downloads or sends."""
    import keyring
    current = config.get_box(alias)
    username = username.strip()
    if not username or not password:
        raise ValueError("Vyplnte prihlasovaci jmeno i heslo.")
    candidate = LoginCandidate(alias, current.box_id, current.environment, username, password)
    verify_sender(candidate)
    data = config.load_config()
    latest = config.get_box(alias)
    if latest != current:
        raise ValueError("Nastaveni uctu se mezitim zmenilo. Otevrete okno znovu.")
    for item in data['boxes']:
        if item['alias'] == alias:
            item['username'] = username
    config.validate_boxes(data)
    keyring.set_password(config.SERVICE, f"{current.environment}:{alias}:{username}", password)
    save_config(data)


def main(alias):
    import tkinter as tk
    from tkinter import ttk
    box = config.get_box(alias)
    root = tk.Tk()
    root.title("Datovka - overeni prihlaseni")
    root.geometry("650x400")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=f"Ucet: {alias}   |   Prostredi: {box.environment}", font=('Segoe UI', 12, 'bold')).pack(anchor='w')
    ttk.Label(frame, text=f"Overovana schranka: {box.box_id}").pack(anchor='w', pady=(4, 12))
    ttk.Label(frame, text="Zadejte udaje, ktere prave fungovaly na webu pres Jmenem a heslem.\nOverime jen identitu schranky. Zadna zprava se nenacte ani neodesle.").pack(anchor='w')
    ttk.Label(frame, text='Prihlasovaci jmeno ISDS:').pack(anchor='w', pady=(12, 2))
    username = tk.StringVar(value=box.username)
    ttk.Entry(frame, textvariable=username, width=50).pack(anchor='w')
    ttk.Label(frame, text='Heslo k datove schrance:').pack(anchor='w', pady=(10, 2))
    password = tk.StringVar()
    entry = ttk.Entry(frame, textvariable=password, show='*', width=50)
    entry.pack(anchor='w')
    status = tk.StringVar(value='Heslo se ulozi az po uspesnem overeni.')
    ttk.Label(frame, textvariable=status, wraplength=590).pack(anchor='w', pady=(14, 6))
    events = queue.Queue()
    status_path = config.private_dir() / 'login-check.json'

    def record(state):
        status_path.write_text(json.dumps({'state': state, 'checked_at': datetime.now(timezone.utc).isoformat(),
                                          'messages_fetched': False}), encoding='utf-8')

    def worker(login, secret):
        try:
            verify_and_save(alias, login, secret)
            events.put(('success', 'Prihlaseni a ID schranky overeno. Udaje byly ulozeny. Okno muzete zavrit.'))
        except PermissionError:
            events.put(('rejected', 'ISDS odmitlo pozadavek (HTTP 401). Webove prihlaseni muze fungovat, ale prihlaseni aplikaci tretich stran muze byt zakazane nebo vyzaduje samostatne pristupove udaje. Puvodni udaje zustaly zachovane.'))
        except Exception as exc:
            # Do not expose SOAP responses, request objects or credential values.
            events.put(('error', f'Overeni nebo ulozeni se nepodarilo ({type(exc).__name__}). Podrobnosti proverime bez vypisu hesla.'))

    def start():
        if not username.get().strip() or not password.get():
            status.set('Vyplnte prihlasovaci jmeno i heslo.')
            return
        login, secret = username.get(), password.get()
        password.set('')
        button.configure(state='disabled')
        status.set('Overuji jednim pozadavkem spojeni s ISDS...')
        record('checking')
        threading.Thread(target=worker, args=(login, secret), daemon=True).start()

    def poll():
        try:
            state, message = events.get_nowait()
            record(state)
            status.set(message)
            if state != 'success':
                button.configure(state='normal')
        except queue.Empty:
            pass
        root.after(200, poll)

    button = ttk.Button(frame, text='Overit prihlaseni a ulozit', command=start)
    button.pack(anchor='w', pady=6)
    record('waiting_for_user')
    root.after(200, poll)
    entry.focus_set()
    root.mainloop()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Mistni overeni a aktualizace prihlaseni bez nacitani zprav.')
    parser.add_argument('alias', help='Nazev existujiciho uctu')
    main(parser.parse_args().alias)
