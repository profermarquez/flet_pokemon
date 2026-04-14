import flet as ft
import requests
import asyncio
import subprocess
import platform

DEFAULT_SERVER_IP = "192.168.100.207"
SERVER_PORT = 8000

def main(page: ft.Page):
    page.title = "PokéDraw Cards"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START

    # Splash screen inicial
    splash = ft.Column([
        ft.Text("🎴", size=80),
        ft.Text("PokéDraw", size=28, weight="bold", color="yellow"),
        ft.Text("Cargando...", size=14, color="grey"),
    ], alignment=ft.MainAxisAlignment.CENTER,
       horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    page.add(splash)
    page.update()

    # Variables de estado
    connection_status = ft.Container(width=14, height=14, bgcolor="red", border_radius=7)
    connection_text = ft.Text("Desconectado", size=12, color="grey")
    status_text = ft.Text("📸 Listo para capturar", size=14, color="grey")
    deck_view = ft.ListView(expand=1, spacing=10, padding=20)
    local_deck = []

    # FilePicker para Android
    picker = ft.FilePicker()
    picker.on_result = lambda e: send_image(e.files[0].path) if e.files else None
    page.overlay.append(picker)
    page.update()

    def pick_file():
        if platform.system() == "Darwin":
            # Mac: osascript por bug de FilePicker en Flet desktop 0.84
            script = 'POSIX path of (choose file with prompt "Seleccionar imagen" of type {"public.image"})'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            path = result.stdout.strip()
            if path:
                send_image(path)
            elif result.stderr:
                status_text.value = f"❌ Error selector: {result.stderr.strip()}"
                page.update()
        else:
            # Android / otros: FilePicker nativo de Flet
            picker.pick_files(allowed_extensions=["png", "jpg", "jpeg"])

    def update_connection_ui(connected: bool, ip: str = None):
        if connected:
            connection_status.bgcolor = "green"
            connection_text.value = f"Conectado • {ip or DEFAULT_SERVER_IP}"
            connection_text.color = "green"
        else:
            connection_status.bgcolor = "red"
            connection_text.value = "Desconectado"
            connection_text.color = "grey"
        page.update()

    def check_connection(ip: str) -> bool:
        try:
            url = f"http://{ip}:{SERVER_PORT}/docs"
            resp = requests.get(url, timeout=3)
            return resp.status_code == 200
        except:
            return False

    def test_connection(e=None):
        ip = server_ip.value.strip()
        status_text.value = "🔍 Probando conexión..."
        page.update()

        if check_connection(ip):
            update_connection_ui(True, ip)
            status_text.value = f"✅ Servidor disponible en {ip}"
        else:
            update_connection_ui(False)
            status_text.value = f"❌ No se pudo conectar a {ip}"
        page.update()

    def on_ip_change(e):
        server_ip_display.value = f"Server: {server_ip.value.strip()}:{SERVER_PORT}"
        page.update()

    # Campo de IP
    server_ip = ft.TextField(
        label="IP del servidor",
        value=DEFAULT_SERVER_IP,
        width=200,
        text_size=14,
        on_change=on_ip_change,
    )

    server_ip_display = ft.Text(f"Server: {DEFAULT_SERVER_IP}:{SERVER_PORT}", size=11, color="blue")

    def send_image(path):
        if not path:
            return

        ip = server_ip.value.strip()

        if not check_connection(ip):
            status_text.value = f"❌ Sin conexión a {ip}"
            update_connection_ui(False)
            page.update()
            return

        status_text.value = "⏳ Enviando a IA..."
        page.update()

        try:
            url = f"http://{ip}:{SERVER_PORT}/analyze"
            with open(path, "rb") as f:
                resp = requests.post(url, files={"file": f}, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    add_card(data)
                    status_text.value = f"✅ {data['name']} | HP:{data['hp']} ATK:{data['attack']}"
                else:
                    status_text.value = f"❌ Error: {data}"
            else:
                status_text.value = f"❌ HTTP {resp.status_code}"
        except Exception as ex:
            status_text.value = f"❌ Error: {str(ex)}"

        page.update()

    def add_card(card):
        local_deck.append(card)
        idx = len(local_deck) - 1

        card_ui = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"🎴 {card['name']}", size=16, weight="bold", color="yellow", expand=1),
                    ft.Text(f"#{idx + 1}", size=11, color="grey"),
                ]),
                ft.Row([
                    ft.Text(f"❤️ HP: {card['hp']}", color="red"),
                    ft.Text(f"⚔️ ATK: {card['attack']}", color="orange"),
                    ft.Text(f"📊 {card['pokemon_score']}", size=12, color="grey"),
                ]),
            ], spacing=4),
            bgcolor="#2a2a35",
            border_radius=12,
            padding=12,
            margin=ft.margin.only(bottom=8),
        )

        deck_view.controls.insert(0, card_ui)
        page.update()

    def start_battle(e):
        ip = server_ip.value.strip()

        if len(local_deck) < 2:
            status_text.value = "⚠️ Necesitas 2 cartas mínimo"
            page.update()
            return

        # Batalla entre las 2 cartas más recientes
        c1, c2 = local_deck[-1]["card_id"], local_deck[-2]["card_id"]
        n1, n2 = local_deck[-1]["name"], local_deck[-2]["name"]
        status_text.value = f"⚔️ {n1} vs {n2}..."
        page.update()

        try:
            resp = requests.get(f"http://{ip}:{SERVER_PORT}/battle/{c1}/{c2}", timeout=10)
            res = resp.json()
            status_text.value = f"🏆 Ganador: {res['winner']}"
        except Exception as ex:
            status_text.value = f"❌ Batalla: {str(ex)}"

        page.update()

    # UI principal
    async def show_main_ui():
        page.controls.clear()
        page.add(
            ft.Row([connection_status, connection_text], alignment=ft.MainAxisAlignment.CENTER),
            server_ip_display,
            ft.Row([
                server_ip,
                ft.IconButton(icon=ft.Icons.REFRESH, on_click=test_connection, tooltip="Probar conexión"),
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([
                ft.Button(
                    "📷 Tomar Dibujo",
                    on_click=lambda _: pick_file(),
                    expand=1,
                ),
                ft.Button("⚔️ Batalla", on_click=start_battle, expand=1),
            ]),
            status_text,
            ft.Divider(),
            ft.Text("📚 Mazo", size=16, weight="bold"),
            deck_view,
        )
        page.update()

    async def delayed_start():
        await asyncio.sleep(1)
        await show_main_ui()

    page.run_task(delayed_start)

if __name__ == "__main__":
    ft.run(main)
