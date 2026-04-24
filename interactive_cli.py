import asyncio
from ac_controller import ACController

async def main():
    print("📡 Fetching current AC status...")
    ctrl = ACController()
    status_result = await ctrl.get_status()
    
    if not status_result.success:
        print(f"❌ Error fetching status: {status_result.message}")
        return
        
    status = status_result.data
    
    print("\n" + "="*30)
    print("  AC Control Panel")
    print("="*30)
    print("Press ENTER to keep the current value, or type a new one.")
    print("-" * 30)
    
    def prompt_value(prompt_text, current_val):
        user_input = input(f"{prompt_text} [{current_val}]: ").strip()
        return user_input if user_input else current_val

    # Prompt user with current values as default
    new_power   = prompt_value("Power (on/off)", status.get('power'))
    new_temp    = prompt_value("Temperature (16-30)", status.get('set_temperature'))
    new_hvac    = prompt_value("HVAC Mode (cool/dry/fan/heat/auto)", status.get('hvac_mode'))
    new_fan     = prompt_value("Fan Mode (auto/low/medium/high/quiet)", status.get('fan_mode'))
    new_v_swing = prompt_value("V-Swing (0=auto, 1-5)", status.get('v_swing'))
    new_h_swing = prompt_value("H-Swing (0=auto, 1-5)", status.get('h_swing'))
    new_preset  = prompt_value("Preset Mode (none/eco/boost/clean)", status.get('preset_mode'))
    new_display = prompt_value("Display Mode (on/off)", status.get('display_mode'))

    print("\n🔄 Applying changes... Please wait.")
    
    # Apply changes only if they differ from current status to avoid spamming MQTT
    if str(new_power).lower() != str(status.get('power')).lower():
        if str(new_power).lower() == 'on':
            await ctrl.turn_on()
        elif str(new_power).lower() == 'off':
            await ctrl.turn_off()
            
    if str(new_temp) != str(status.get('set_temperature')):
        await ctrl.set_temp(new_temp)
        
    if str(new_hvac).lower() != str(status.get('hvac_mode')).lower():
        await ctrl.set_hvac_mode(new_hvac)
        
    if str(new_fan).lower() != str(status.get('fan_mode')).lower():
        await ctrl.set_fan_mode(new_fan)
        
    if str(new_v_swing) != str(status.get('v_swing')):
        await ctrl.set_v_swing(new_v_swing)
        
    if str(new_h_swing) != str(status.get('h_swing')):
        await ctrl.set_h_swing(new_h_swing)
        
    if str(new_preset).lower() != str(status.get('preset_mode')).lower():
        await ctrl.set_preset_mode(new_preset)
        
    if str(new_display).lower() != str(status.get('display_mode')).lower():
        await ctrl.set_display_mode(new_display)
        
    print("✅ Done! Changes have been sent to the AC.")
    print("Note: Some modes take a few seconds to reflect on the device.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
