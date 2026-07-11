import subprocess
import time
import os
import sys
import asyncio
import winrt.windows.devices.bluetooth as wdb
import winrt.windows.devices.enumeration as wde
import winrt.windows.devices.radios as wdr

def is_process_running(process_name: str) -> bool:
    """
    Checks if a process is running on Windows by querying the 'tasklist' command.
    Using the built-in Windows utility 'tasklist' avoids adding third-party dependencies 
    like psutil, making the setup lightweight and standard-library only.
    """
    try:
        # Filter tasklist by image name to minimize output parsing overhead
        output = subprocess.check_output(
            f'tasklist /FI "IMAGENAME eq {process_name}"', 
            shell=True, 
            text=True
        )
        return process_name.lower() in output.lower()
    except Exception:
        return False

async def enable_bluetooth_radio() -> bool:
    """
    Checks the status of the system's Bluetooth radio.
    If it is turned off, programmatically turns it on.
    Does not require administrator privileges.
    """
    try:
        radios = await wdr.Radio.get_radios_async()
        for r in radios:
            if r.kind == wdr.RadioKind.BLUETOOTH:
                if r.state != wdr.RadioState.ON:
                    print("[Bluetooth] Laptop radio is OFF. Toggling ON...")
                    await r.set_state_async(wdr.RadioState.ON)
                    print("[Bluetooth] Radio enabled successfully.")
                    # Sleep briefly to let the hardware controller initialize
                    await asyncio.sleep(1.5)
                    return True
                else:
                    print("[Bluetooth] Laptop radio is already ON.")
                    return True
        print("[Bluetooth Warning] No Bluetooth radio found on this laptop.")
        return False
    except Exception as e:
        print(f"[Bluetooth Error] Failed to enable radio: {e}")
        return False

def connect_bluetooth_device(device_name: str) -> bool:
    """
    Triggers Windows to connect to a paired Bluetooth device by name using native Python WinRT APIs.
    Does not require administrator privileges, third-party tools, or PowerShell.
    """
    async def _trigger():
        try:
            # First, ensure the laptop's Bluetooth radio is enabled
            await enable_bluetooth_radio()
            
            print(f"[Bluetooth] Searching for paired speaker: '{device_name}'...")
            selector = wdb.BluetoothDevice.get_device_selector()
            # Call the exact overloaded WinRT function name in Python
            devices = await wde.DeviceInformation.find_all_async_aqs_filter(selector)
            
            target_device = None
            for device in devices:
                if device_name.lower() in device.name.lower():
                    target_device = device
                    break
                    
            if target_device:
                print(f"[Bluetooth] Found paired device: '{target_device.name}'. Triggering WinRT connection...")
                # Attempt to instantiate (which triggers Windows to connect)
                bt_device = await wdb.BluetoothDevice.from_id_async(target_device.id)
                # Check status: 0 = Disconnected, 1 = Connected
                status = bt_device.connection_status
                status_str = "Connected" if status == 1 else "Disconnected"
                print(f"[Bluetooth] Connection status: {status_str}")
                return status == 1
            else:
                print(f"[Bluetooth] Device '{device_name}' not found in paired list.")
                return False
        except OSError as e:
            # WinError -2147020577 is 'The device is not ready for use' (physically powered off)
            if "[WinError -2147020577]" in str(e) or getattr(e, 'winerror', None) == -2147020577:
                print(f"[Bluetooth] Device '{device_name}' is physically turned off or out of range.")
            else:
                print(f"[Bluetooth] Connection failed: {e}")
            return False
        except Exception as e:
            print(f"[Bluetooth Error] Unexpected error: {e}")
            return False

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_trigger())
    finally:
        loop.close()

def run_watcher():
    """
    Background process watcher.
    Monitors Spotify.exe and manages system lifecycle events:
    - Automatically connects to configured Bluetooth speaker.
    - Launches main.py headlessly when Spotify.exe opens.
    - Kills main.py when Spotify.exe closes.
    - Detects if main.py crashed internally and resets state for auto-recovery.
    """
    spotify_process = "Spotify.exe"
    main_script = "main.py"
    
    # Hardcoded Bluetooth speaker name
    bluetooth_device = "Kush's JBL Go 4"
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    # Using python.exe (with CREATE_NEW_CONSOLE creation flag) to open a visible logging terminal for developer inspection
    python_exe = os.path.join(project_dir, "venv", "Scripts", "python.exe")
    script_path = os.path.join(project_dir, main_script)
    
    daemon_process = None
    print(f"[Watcher] Monitoring started for '{spotify_process}'.")

    while True:
        try:
            spotify_active = is_process_running(spotify_process)
            
            # Case 1: Spotify is running but daemon is not -> START
            if spotify_active and daemon_process is None:
                print(f"[Watcher] Spotify started.")
                
                # Connect to Bluetooth speaker if configured
                if bluetooth_device:
                    connect_bluetooth_device(bluetooth_device)
                    # Brief sleep to allow Bluetooth audio handshaking to establish before starting playback
                    time.sleep(2)
                
                print(f"[Watcher] Spawning voice assistant in a new terminal window...")
                # Popen launches main.py in a dedicated console window so you can inspect output logs
                daemon_process = subprocess.Popen(
                    [python_exe, "-u", script_path],
                    cwd=project_dir,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                
            # Case 2: Spotify is closed but daemon is running -> STOP
            elif not spotify_active and daemon_process is not None:
                print(f"[Watcher] Spotify closed. Terminating voice assistant...")
                daemon_process.terminate()
                daemon_process.wait()  # Prevent zombie/orphan process handles
                daemon_process = None
                
            # Case 3: Daemon is running, check if it crashed internally (Auto-Recovery)
            elif daemon_process is not None:
                if daemon_process.poll() is not None:
                    print(f"[Watcher] Warning: Voice daemon exited unexpectedly. Resetting status...")
                    daemon_process = None
                    
            # Check every 4 seconds to minimize CPU footprint while remaining responsive
            time.sleep(4)
            
        except KeyboardInterrupt:
            print("\n[Watcher] Exiting. Cleaning up child processes...")
            if daemon_process is not None:
                daemon_process.terminate()
            break
        except Exception as e:
            print(f"[Watcher Error] {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_watcher()
