from pynput import keyboard
import sys

def on_press(key):
    try:
        if hasattr(key, 'char'):
            print(f"Char: {key.char!r}")
        else:
            print(f"Key: {key}")
    except Exception as e:
        print(f"Error: {e}")

def on_release(key):
    if key == keyboard.Key.esc:
        print("ESC pressed, exiting")
        return False

print("Press keys (ESC to stop). Try Windows keys, then press ESC...")
sys.stdout.flush()
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
