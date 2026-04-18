#!/usr/bin/env python3
"""
Interactive Chat Client for Claude Code OpenAI Wrapper
Starts the server in the background and provides a rich TUI for chatting.
"""

import subprocess
import time
import os
import signal
import sys
import httpx
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt

# Configuration
DEFAULT_PORT = 8000
API_KEY = os.getenv("API_KEY", "dev-token-123")  # Pre-set key to bypass interactive prompt


def new_session_id():
    """Create a fresh session id for the wrapper."""
    return f"chat-{int(time.time() * 1000)}"

def find_available_port(start_port):
    import socket
    port = start_port
    while port < start_port + 10:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
        port += 1
    return start_port

def start_server(port):
    """Start the API server as a background process."""
    console = Console()
    console.print(f"🚀 [bold blue]Starting server on port {port}...[/bold blue]")
    
    env = os.environ.copy()
    env["API_KEY"] = API_KEY
    env["PORT"] = str(port)
    env["DEBUG_MODE"] = "false"
    
    # Try to use poetry run if available
    try:
        subprocess.run(["poetry", "--version"], capture_output=True, check=True)
        cmd = ["poetry", "run", "python", "-m", "src.main", str(port)]
    except (subprocess.CalledProcessError, FileNotFoundError):
        cmd = [sys.executable, "-m", "src.main", str(port)]

    # Use start_new_session to make it a process group leader
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True
    )
    
    # Wait for the health check
    health_url = f"http://localhost:{port}/health"
    max_wait = 30
    start_time = time.time()
    
    with console.status("[bold green]Waiting for server to initialize...[/bold green]") as status:
        while time.time() - start_time < max_wait:
            if process.poll() is not None:
                # Process died
                out, _ = process.communicate()
                console.print(f"[bold red]Server failed to start:[/bold red]\n{out}")
                sys.exit(1)
            try:
                resp = httpx.get(health_url, timeout=1.0)
                if resp.status_code == 200:
                    console.print(f"✅ [bold green]Server is ready at http://localhost:{port}[/bold green]")
                    return process
            except (httpx.ConnectError, httpx.RequestError):
                pass
            time.sleep(1)
            
    process.terminate()
    console.print("[bold red]Timeout waiting for server to start.[/bold red]")
    sys.exit(1)

def chat_loop(client, default_model):
    """Main interactive chat loop."""
    console = Console()
    console.print(Panel.fit(
        "[bold green]Welcome to the Claude Interactive Chat![/bold green]\n"
        "Features: Background Server, Streaming, Markdown Rendering\n\n"
        "Commands:\n"
        "  [bold cyan]/model[/bold cyan] - Change the model\n"
        "  [bold cyan]/clear[/bold cyan] - Clear conversation history\n"
        "  [bold cyan]/exit[/bold cyan]  - Quit the chat",
        title="Settings"
    ))

    messages = []
    current_model = default_model
    session_id = new_session_id()
    
    while True:
        try:
            user_input = Prompt.ask(f"\n[bold blue]({current_model}) You[/bold blue]")
            
            if not user_input.strip():
                continue
                
            if user_input.lower() in ["/exit", "exit", "quit"]:
                break
                
            if user_input.startswith("/model"):
                parts = user_input.split()
                if len(parts) > 1:
                    current_model = parts[1]
                    messages = []
                    session_id = new_session_id()
                    console.print(
                        f"🔄 Model changed to [bold cyan]{current_model}[/bold cyan] "
                        "and conversation reset."
                    )
                else:
                    console.print("[yellow]Usage: /model <model_name>[/yellow]")
                    console.print("[dim]Example: /model claude-sonnet-4-6[/dim]")
                continue
                
            if user_input == "/clear":
                messages = []
                session_id = new_session_id()
                console.print("✨ Conversation history cleared. Started a new session.")
                continue

            messages.append({"role": "user", "content": user_input})
            
            console.print("\n[bold magenta]Assistant[/bold magenta]")
            
            full_response = ""
            with Live(Markdown(""), refresh_per_second=10, console=console) as live:
                try:
                    stream = client.chat.completions.create(
                        model=current_model,
                        messages=messages,
                        stream=True,
                        extra_body={"session_id": session_id}
                    )
                    
                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            full_response += chunk.choices[0].delta.content
                            live.update(Markdown(full_response))
                except Exception as e:
                    live.update(f"[bold red]Error:[/bold red] {str(e)}")
                    continue
            
            messages.append({"role": "assistant", "content": full_response})
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
            continue
        except EOFError:
            break

if __name__ == "__main__":
    port = find_available_port(DEFAULT_PORT)
    server_proc = None
    
    try:
        server_proc = start_server(port)
        
        client = OpenAI(
            base_url=f"http://localhost:{port}/v1",
            api_key=API_KEY
        )
        
        # Default to Claude unless specified
        default_model = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
        
        chat_loop(client, default_model)
        
    finally:
        if server_proc:
            print("\n🛑 Shutting down server...")
            # Kill the whole process group
            try:
                os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
            except Exception:
                server_proc.terminate()
            print("Done.")
