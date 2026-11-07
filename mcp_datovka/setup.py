"""Interactive configuration and review. No password arguments or MCP approval."""
import argparse
import getpass
import json
import os
import tempfile
import sys
import re
from pathlib import Path
from . import config, drafts


def save_config(data: dict) -> None:
    root = config.private_dir()
    root.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        os.replace(temp, root / "config.json")
    finally:
        if Path(temp).exists():
            Path(temp).unlink()


def add_account():
    import keyring
    data = config.load_config()
    while True:
        entered = input("Nazev uctu (napr. osobni, firma nebo FO): ").strip()
        alias = entered.lower()
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", alias):
            if alias != entered:
                print(f"Nazev uctu bude ulozen jako: {alias}")
            break
        print("Pouzijte 1 az 40 pismen bez diakritiky, cislic nebo pomlcek; nezacinejte pomlckou.")
    if any(b["alias"] == alias for b in data["boxes"]):
        raise ValueError("Ucet uz existuje; pouzijte novy nazev nebo upravte mistni konfiguraci.")
    box = {"alias": alias, "box_id": input("ID schranky: ").strip(),
           "username": input("Prihlasovaci jmeno ISDS (nikoli e-mail): ").strip(),
           "environment": "production" if input("Pro ostre prostredi napiste production, jinak test: ").strip() == "production" else "test",
           "allow_receive": False, "allow_send": False}
    print("Nacitani zprav muze zpusobit jejich doruceni a beh lhut.")
    box["allow_receive"] = input("Povolit prijem? Napiste ANO: ").strip() == "ANO"
    box["allow_send"] = input("Povolit odesilani po schvaleni kazdeho navrhu? Napiste ANO: ").strip() == "ANO"
    candidate = {**data, "boxes": data["boxes"] + [box]}
    # Validate in memory, without writing a temporarily invalid config.
    config.validate_boxes(candidate)
    password = getpass.getpass("Heslo ISDS (ulozi se do systemoveho uloziste): ")
    if not password:
        raise ValueError("Prazdne heslo neni dovoleno.")
    keyring.set_password(config.SERVICE, f"{box['environment']}:{alias}:{box['username']}", password)
    save_config(candidate)
    print("Ucet ulozen. Spojeni s ISDS zatim nebylo overeno.")


def review(draft_id: str):
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
    snapshot = drafts.preview(draft_id)
    root = tk.Tk()
    root.title("Datovka: kontrola navrhu pred odeslanim")
    root.geometry("850x680")
    tk.Label(root, text="Zkontrolujte odesilatele, prijemce, uplny text a prilohy.\nSchvaleni plati 15 minut a samo zpravu neodesle.").pack(pady=10)
    view = scrolledtext.ScrolledText(root, wrap="word")
    view.pack(fill="both", expand=True, padx=12)
    view.insert("1.0", json.dumps(snapshot, ensure_ascii=False, indent=2))
    view.configure(state="disabled")

    def approve():
        try:
            drafts.approve(draft_id, snapshot["digest"])
        except Exception as exc:
            messagebox.showerror("Nelze schvalit", str(exc))
            return
        messagebox.showinfo("Schvaleno", "Navrh je schvaleny pro jeden pokus o odeslani.")
        root.destroy()

    tk.Button(root, text="Schvaluji tento navrh", command=approve).pack(pady=8)
    tk.Button(root, text="Zavrit bez schvaleni", command=root.destroy).pack(pady=4)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Mistni nastaveni Datovky bez hesel v chatu.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("add")
    sub.add_parser("status")
    sub.add_parser("review").add_argument("draft_id")
    args = parser.parse_args()
    if args.command == "init":
        if not (config.private_dir() / "config.json").exists():
            save_config({"version": 1, "boxes": []})
        (config.private_dir() / "runtime.json").write_text(
            json.dumps({"python": sys.executable}), encoding="utf-8")
        print("Soukroma konfigurace pripravena:", config.private_dir())
    elif args.command == "add":
        add_account()
    elif args.command == "review":
        review(args.draft_id)
    else:
        print(json.dumps({"accounts": len(config.get_boxes()), "connected": False}, indent=2))


if __name__ == "__main__":
    main()
