#!/usr/bin/env python3

import curses
import ipaddress
import os
import subprocess
import logging

# ------------------ Phase 1 Logger ------------------ #
phase1_logger = logging.getLogger("phase1_logger")
phase1_logger.setLevel(logging.INFO)
phase1_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
phase1_file_handler = logging.FileHandler('phase1.log')
phase1_file_handler.setLevel(logging.INFO)
phase1_file_handler.setFormatter(phase1_formatter)
phase1_logger.addHandler(phase1_file_handler)

# ------------------ Phase 2 Logger ------------------ #
phase2_logger = logging.getLogger("phase2_logger")
phase2_logger.setLevel(logging.INFO)
phase2_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
phase2_file_handler = logging.FileHandler('phase2.log')
phase2_file_handler.setLevel(logging.INFO)
phase2_file_handler.setFormatter(phase2_formatter)
phase2_logger.addHandler(phase2_file_handler)

##############################################
# Common Helper Functions (Printing, Input)  #
##############################################

def print_wrapped(screen, start_y, start_x, text, max_width):
    """
    Print text at (start_y, start_x) with truncation if needed.
    Helps maintain alignment in limited terminal widths.
    """
    if len(text) > max_width:
        text = text[:max_width-1]
    screen.addstr(start_y, start_x, text)

def message_box(screen, message):
    """
    Display a message in a box. The user presses a key to continue.
    Useful for confirmations, errors, or notifications.
    """
    screen.clear()
    screen.border(0)
    lines = message.split('\n')
    max_y, max_x = screen.getmaxyx()
    y = 2
    for line in lines:
        if y >= max_y - 2:
            break
        print_wrapped(screen, y, 2, line, max_x - 4)
        y += 1
    if y < max_y - 2:
        print_wrapped(screen, y+1, 2, "Press any key to continue...", max_x - 4)
    screen.refresh()
    screen.getch()

def input_box(screen, prompt):
    """
    Prompt user for input with a single line. 
    Press ESC or type 'back' to return None (go back).
    """
    curses.noecho()
    screen.clear()
    screen.border(0)
    max_y, max_x = screen.getmaxyx()
    lines = prompt.split('\n')
    y = 2
    for line in lines:
        if y >= max_y - 2:
            break
        print_wrapped(screen, y, 2, line, max_x - 4)
        y += 1

    print_wrapped(screen, y+1, 2, "(Press ESC or type 'back' to return)", max_x - 4)
    input_y = y + 3
    input_x = 2
    screen.move(input_y, input_x)
    screen.refresh()

    buffer = []
    curses.curs_set(1)
    while True:
        ch = screen.getch()
        if ch == 27:  # ESC
            curses.curs_set(0)
            return None
        elif ch in (curses.KEY_BACKSPACE, 127):
            if buffer:
                buffer.pop()
                screen.delch(input_y, input_x + len(buffer))
        elif ch in (10, 13):  # Enter
            user_input = "".join(buffer).strip()
            curses.curs_set(0)
            if user_input.lower() == "back":
                return None
            return user_input
        elif ch in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN):
            continue
        else:
            if 32 <= ch <= 126:
                buffer.append(chr(ch))
                screen.addch(input_y, input_x + len(buffer)-1, ch)

def run_command(cmd):
    """
    Run a shell command quietly, raise on failure.
    """
    with open(os.devnull, 'w') as devnull:
        subprocess.check_call(cmd, stdout=devnull, stderr=devnull)

##################################
# Phase 1: Network Configuration #
##################################

def validate_ip(ip_str):
    """Check if ip_str is a valid IPv4 address."""
    try:
        ipaddress.IPv4Address(ip_str)
        return True
    except:
        return False

def get_network_interfaces():
    """Return list of interfaces from /sys/class/net."""
    return os.listdir('/sys/class/net/')

def route_exists(destination_cidr, gateway, interface_name):
    """Check if a route exists in the system routing table."""
    output = subprocess.check_output(['ip', 'route', 'show'], universal_newlines=True)
    route_line = f"{destination_cidr} via {gateway} dev {interface_name}"
    return route_line in output


def add_route_temporary(interface_name, destination_cidr, gateway):
    cmd = ['ip', 'route', 'add', destination_cidr, 'via', gateway, 'dev', interface_name]
    subprocess.check_call(cmd)
    if not route_exists(destination_cidr, gateway, interface_name):
        raise ValueError("Route not found after addition.")

def add_route_permanent(interface_name, destination_cidr, gateway):
    run_command(['nmcli', 'connection', 'modify', interface_name, '+ipv4.routes', f"{destination_cidr} {gateway}"])
    run_command(['nmcli', 'connection', 'up', interface_name])
    if not route_exists(destination_cidr, gateway, interface_name):
        raise ValueError("Route not found after permanent addition.")

def remove_route_temporary(interface_name, destination_cidr, gateway):
    if not route_exists(destination_cidr, gateway, interface_name):
        raise ValueError("Route does not exist.")
    cmd = ['ip', 'route', 'del', destination_cidr, 'via', gateway, 'dev', interface_name]
    subprocess.check_call(cmd)

def change_dns(interface_name, dns_list, permanent):
    if permanent:
        run_command(['nmcli', 'connection', 'modify', interface_name, 'ipv4.dns', ','.join(dns_list)])
        run_command(['nmcli', 'connection', 'up', interface_name])
    else:
        for dns in dns_list:
            run_command(['resolvectl', 'dns', interface_name, dns])

def change_hostname(new_hostname):
    run_command(['hostnamectl', 'set-hostname', new_hostname])

def set_static_ip(interface_name, ip_address, subnet_mask, gateway, permanent):
    cidr = f"{ip_address}/{subnet_mask}"
    if permanent:
        run_command(['nmcli', 'connection', 'modify', interface_name, 'ipv4.addresses', cidr])
        if gateway:
            run_command(['nmcli', 'connection', 'modify', interface_name, 'ipv4.gateway', gateway])
        run_command(['nmcli', 'connection', 'modify', interface_name, 'ipv4.method', 'manual'])
        run_command(['nmcli', 'connection', 'up', interface_name])
    else:
        run_command(['ip', 'addr', 'flush', 'dev', interface_name])
        run_command(['ip', 'addr', 'add', cidr, 'dev', interface_name])
        if gateway:
            run_command(['ip', 'route', 'add', 'default', 'via', gateway, 'dev', interface_name])

def use_dhcp(interface_name):
    run_command(['nmcli', 'connection', 'modify', interface_name, 'ipv4.method', 'auto'])
    run_command(['nmcli', 'connection', 'up', interface_name])

################################
# Phase 1: TUI Menu and Forms  #
################################

import curses

phase1_logger = logging.getLogger("phase1_logger")

def select_interface(screen):
    interfaces = get_network_interfaces()
    selected = 0
    while True:
        screen.clear()
        screen.border(0)
        print_wrapped(screen, 2, 2, "Select Interface (ESC to go back)", screen.getmaxyx()[1]-4)
        for idx, iface in enumerate(interfaces):
            prefix = "> " if idx == selected else "  "
            print_wrapped(screen, 4+idx, 2, prefix + iface, screen.getmaxyx()[1]-4)
        key = screen.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(interfaces) - 1:
            selected += 1
        elif key in [10, 13]:
            return interfaces[selected]
        elif key == 27:
            return None

def select_permanence(screen):
    options = ["Temporarily", "Permanently", "Back"]
    selected = 0
    while True:
        screen.clear()
        screen.border(0)
        print_wrapped(screen, 2, 2, "Apply Change:", screen.getmaxyx()[1]-4)
        for idx, option in enumerate(options):
            prefix = "> " if idx == selected else "  "
            print_wrapped(screen, 4+idx, 2, prefix + option, screen.getmaxyx()[1]-4)
        key = screen.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(options) - 1:
            selected += 1
        elif key in [10, 13]:
            if options[selected] == "Back":
                return None
            return (selected == 1)
        elif key == 27:
            return None

def change_dns_form(screen):
    while True:
        interface = select_interface(screen)
        if interface is None:
            return
        while True:
            dns_servers = input_box(screen, "Enter up to 3 DNS Servers (comma-separated):")
            if dns_servers is None:
                break
            if dns_servers == '':
                message_box(screen, "DNS Servers cannot be empty!")
                continue
            dns_list = [dns.strip() for dns in dns_servers.split(',') if dns.strip()]
            if len(dns_list) == 0:
                message_box(screen, "No valid DNS servers entered!")
                continue
            if len(dns_list) > 3:
                message_box(screen, "You entered more than 3 DNS servers.")
                continue

            # Validate each DNS
            all_good = True
            for d in dns_list:
                if not validate_ip(d):
                    all_good = False
                    message_box(screen, f"Invalid DNS IP: {d}")
                    break
            if not all_good:
                continue

            p = select_permanence(screen)
            if p is None:
                break
            permanent = p
            try:
                change_dns(interface, dns_list, permanent)
                message_box(screen, "DNS updated successfully!")
                phase1_logger.info(f"DNS updated to {dns_list} on {interface}, permanent={permanent}")
                return
            except Exception as e:
                phase1_logger.error(f"Error updating DNS: {e}")
                message_box(screen, f"Error: {e}")
        return

def change_hostname_form(screen):
    while True:
        newname = input_box(screen, "Enter New Hostname:")
        if newname is None:
            return
        if not newname:
            message_box(screen, "Hostname cannot be empty!")
            continue
        try:
            change_hostname(newname)
            message_box(screen, "Hostname changed successfully!")
            phase1_logger.info(f"Hostname changed to {newname}")
            return
        except Exception as e:
            phase1_logger.error(f"Error changing hostname: {e}")
            message_box(screen, f"Error: {e}")

def set_static_ip_form(screen):
    while True:
        interface = select_interface(screen)
        if interface is None:
            return

        while True:
            ip_address = input_box(screen, "Enter IP Address (e.g. 192.168.1.10):")
            if ip_address is None:
                return
            if not validate_ip(ip_address):
                message_box(screen, "Invalid IP address!")
                continue
            break

        while True:
            subnet_mask = input_box(screen, "Enter Subnet Mask in CIDR (0-32):")
            if subnet_mask is None:
                return
            if not subnet_mask.isdigit():
                message_box(screen, "Subnet mask must be a number.")
                continue
            mask_int = int(subnet_mask)
            if mask_int < 0 or mask_int > 32:
                message_box(screen, "Subnet mask out of range (0-32)!")
                continue
            break

        gateway = ''
        while True:
            gw = input_box(screen, "Enter Gateway IP (Optional):")
            if gw is None:
                return
            if gw == '':
                gateway = ''
                break
            if not validate_ip(gw):
                message_box(screen, "Invalid Gateway IP!")
                continue
            # Check if gateway is in same network
            try:
                network = ipaddress.ip_network(f"{ip_address}/{mask_int}", strict=False)
                if ipaddress.IPv4Address(gw) not in network:
                    message_box(screen, "Gateway not in same subnet!")
                    continue
            except:
                pass
            gateway = gw
            break

        perm = select_permanence(screen)
        if perm is None:
            return
        permanent = perm

        try:
            set_static_ip(interface, ip_address, mask_int, gateway, permanent)
            message_box(screen, "Static IP set successfully!")
            phase1_logger.info(f"Set static IP {ip_address}/{mask_int} on {interface}, permanent={permanent}")
            return
        except Exception as e:
            phase1_logger.error(f"Error setting static IP: {e}")
            message_box(screen, f"Error: {e}")

def use_dhcp_form(screen):
    while True:
        iface = select_interface(screen)
        if iface is None:
            return
        try:
            use_dhcp(iface)
            message_box(screen, "DHCP enabled permanently!")
            phase1_logger.info(f"DHCP enabled on {iface}")
            return
        except Exception as e:
            phase1_logger.error(f"Error enabling DHCP: {e}")
            message_box(screen, f"Error: {e}")

def add_route_form(screen):
    while True:
        iface = select_interface(screen)
        if iface is None:
            return

        while True:
            dest_ip = input_box(screen, "Destination Network IP (e.g. 192.168.1.0):")
            if dest_ip is None:
                return
            if not validate_ip(dest_ip):
                message_box(screen, "Invalid Destination IP!")
                continue
            break

        while True:
            dest_mask = input_box(screen, "Enter Destination Network Mask (0-32):")
            if dest_mask is None:
                return
            if not dest_mask.isdigit():
                message_box(screen, "Subnet mask must be numeric!")
                continue
            dm = int(dest_mask)
            if dm < 0 or dm > 32:
                message_box(screen, "Invalid mask range (0-32).")
                continue
            break

        cidr = f"{dest_ip}/{dm}"

        while True:
            gw = input_box(screen, "Enter Gateway IP:")
            if gw is None:
                return
            if not validate_ip(gw):
                message_box(screen, "Invalid Gateway IP.")
                continue
            break

        perm = select_permanence(screen)
        if perm is None:
            return
        permanent = perm
        try:
            if permanent:
                add_route_permanent(iface, cidr, gw)
            else:
                add_route_temporary(iface, cidr, gw)
            message_box(screen, "Route added successfully!")
            phase1_logger.info(f"Added route {cidr} via {gw} on {iface}, perm={permanent}")
            return
        except ValueError as ve:
            message_box(screen, str(ve))
        except subprocess.CalledProcessError as cpe:
            phase1_logger.error(f"Error adding route: {cpe}")
            message_box(screen, f"Error: {cpe}")

def remove_route_form(screen):
    while True:
        iface = select_interface(screen)
        if iface is None:
            return

        while True:
            dest_ip = input_box(screen, "Destination Network IP of route to remove:")
            if dest_ip is None:
                return
            if not validate_ip(dest_ip):
                message_box(screen, "Invalid Destination IP!")
                continue
            break

        while True:
            dest_mask = input_box(screen, "Enter Destination Network Mask (0-32):")
            if dest_mask is None:
                return
            if not dest_mask.isdigit():
                message_box(screen, "Subnet mask must be numeric!")
                continue
            dm = int(dest_mask)
            if dm < 0 or dm > 32:
                message_box(screen, "Invalid mask range!")
                continue
            break

        cidr = f"{dest_ip}/{dm}"

        while True:
            gw = input_box(screen, "Enter Gateway IP of route to remove:")
            if gw is None:
                return
            if not validate_ip(gw):
                message_box(screen, "Invalid Gateway IP.")
                continue
            break

        try:
            remove_route_temporary(iface, cidr, gw)
            message_box(screen, "Route removed successfully!")
            phase1_logger.info(f"Removed route {cidr} via {gw} on {iface}")
            return
        except ValueError as ve:
            message_box(screen, str(ve))
        except subprocess.CalledProcessError as cpe:
            phase1_logger.error(f"Error removing route: {cpe}")
            message_box(screen, f"Error: {cpe}")

def network_configuration_menu(screen):
    """
    Phase 1 menu for DNS, Hostname, Static IP, DHCP, Routes.
    """
    selected = 0
    options = [
        "Change DNS",
        "Change Hostname",
        "Set Static IP",
        "Use DHCP",
        "Add Route",
        "Remove Route",
        "Back to Main Menu"
    ]
    while True:
        screen.clear()
        screen.border(0)
        print_wrapped(screen, 2, 2, "Network Configuration Menu (ESC to go back)", screen.getmaxyx()[1]-4)
        for idx, opt in enumerate(options):
            prefix = "> " if idx == selected else "  "
            print_wrapped(screen, 4+idx, 2, prefix + opt, screen.getmaxyx()[1]-4)
        key = screen.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(options) - 1:
            selected += 1
        elif key in [10, 13]:
            if selected == 0:
                change_dns_form(screen)
            elif selected == 1:
                change_hostname_form(screen)
            elif selected == 2:
                set_static_ip_form(screen)
            elif selected == 3:
                use_dhcp_form(screen)
            elif selected == 4:
                add_route_form(screen)
            elif selected == 5:
                remove_route_form(screen)
            elif selected == 6:
                break
        elif key == 27:
            break

##################################
# Phase 2: Nftables Management   #
##################################

def flush_all_rules():
    """
    Flush all existing nftables rules (as a last resort).
    """
    try:
        subprocess.check_call(["nft", "flush", "ruleset"])
        phase2_logger.info("Flushed all nftables ruleset.")
    except Exception as e:
        phase2_logger.error(f"Failed to flush ruleset: {e}")

def remove_and_reinstall_nftables():
    """
    Remove and reinstall nftables completely.
    """
    try:
        run_command(["apt-get", "remove", "-y", "nftables"])
        run_command(["apt-get", "purge", "-y", "nftables"])
        run_command(["apt-get", "autoremove", "-y"])
        run_command(["apt-get", "install", "-y", "nftables"])
        phase2_logger.info("Successfully removed and reinstalled nftables.")
    except Exception as e:
        phase2_logger.error(f"Failed to remove/reinstall nftables: {e}")

def final_nft_attempt(screen):
    """
    After a flush or remove/reinstall attempt, do final tries to start service.
    """
    try:
        run_command(["systemctl", "enable", "nftables"])
        run_command(["systemctl", "start", "nftables"])
        phase2_logger.info("Finally started nftables.service after last resort.")
    except Exception as e:
        phase2_logger.error(f"Last resort attempt failed to start nftables: {e}")
        message_box(screen, "Could not start nftables even after last resort.\nRules will not apply properly.")
def ensure_nftables_conf(screen):
    """
    Ensure /etc/nftables.conf has minimal definitions for 'inet filter'
    and 'ip nat'. If the file doesn't exist or is empty, create a default
    config. Adjust as needed for your environment.
    """
    conf_path = "/etc/nftables.conf"

    # If the file doesn't exist or is empty, create a basic config
    if not os.path.exists(conf_path) or os.path.getsize(conf_path) == 0:
        default_conf = """#!/usr/sbin/nft -f
flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy accept;
    }
}

table ip nat {
    chain prerouting {
        type nat hook prerouting priority 0; policy accept;
    }

    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
    }
}
"""
        try:
            with open(conf_path, 'w') as f:
                f.write(default_conf)
            # If you want to log success, do so here:
            # phase2_logger.info("Created a default /etc/nftables.conf with basic filter and nat config.")
        except Exception as e:
            # If there's a logging mechanism, you can log or show the error
            # For example:
            # phase2_logger.error(f"Error creating /etc/nftables.conf: {e}")
            # And possibly show a message to the user:
            message_box(screen, f"Error creating {conf_path}:\n{e}")

def check_nft_installed_phase2(screen):
    """
    Enhanced check for nft:
    1) which nft
    2) apt-get install if missing
    3) systemctl is-active ...
    4) if fails, flush all rules, remove & reinstall, final attempt
    """
    # 1) Check if nft is present
    have_nft = True
    try:
        subprocess.check_output(["which", "nft"], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        message_box(screen, "nft command not found.\nAttempting to install nftables.")
        try:
            run_command(["apt-get", "update"])
            run_command(["apt-get", "install", "-y", "nftables"])
            phase2_logger.info("Successfully installed nftables.")
        except Exception as e:
            phase2_logger.error(f"Failed to install nftables: {e}")
            return False

    # 2) Check service
    try:
        status = subprocess.check_output(["systemctl", "is-active", "nftables"], universal_newlines=True).strip()
        if status != "active":
            # Try enable & start
            try:
                run_command(["systemctl", "enable", "nftables"])
                run_command(["systemctl", "start", "nftables"])
                phase2_logger.info("Enabled & started nftables.service.")
            except Exception as e:
                # Attempt flush + remove & reinstall
                phase2_logger.warning(f"Failed to enable/start nftables.service initially:\n{e}")
                flush_all_rules()
                remove_and_reinstall_nftables()
                final_nft_attempt(screen)
    except subprocess.CalledProcessError as se:
        # systemctl is-active failed
        phase2_logger.warning(f"systemctl is-active nftables failed: {se}")
        flush_all_rules()
        remove_and_reinstall_nftables()
        final_nft_attempt(screen)

    # 3) Ensure minimal config
    ensure_nftables_conf(screen)
    return True

def apply_nft_rule(screen, rule, nat=False):
    """
    Append rule to /etc/nftables.conf, then do `nft -f /etc/nftables.conf`.
    If nat=True, place the rule in ip nat postrouting/prerouting as needed.
    If nat=False, place it in inet filter input.
    """
    conf_path = "/etc/nftables.conf"
    if nat:
        if "masquerade" in rule:
            full_rule = f"add rule ip nat postrouting {rule}\n"
        elif "dnat to" in rule:
            full_rule = f"add rule ip nat prerouting {rule}\n"
        else:
            phase2_logger.error("Unknown NAT rule pattern: " + rule)
            message_box(screen, "Error: Unknown NAT rule pattern.")
            return
    else:
        full_rule = f"add rule inet filter input {rule}\n"

    try:
        with open(conf_path, 'a') as f:
            f.write(full_rule)

        run_command(["nft", "-f", conf_path])
        message_box(screen, "Rule added successfully!")
        phase2_logger.info(f"Added nftables rule: {full_rule.strip()}")
    except Exception as e:
        phase2_logger.error(f"Error applying nft rule: {e}")
        message_box(screen, f"Error applying rule:\n{e}")

###############
# RULE FORMS  #
###############

def validate_ip_input_phase2(screen, prompt):
    while True:
        val = input_box(screen, prompt)
        if val is None:
            return None
        try:
            ipaddress.IPv4Address(val)
            return val
        except:
            message_box(screen, f"Invalid IP: {val}")
            continue

def ct_state_rule_form(screen):
    allowed_states = ["established", "related", "invalid", "new"]
    allowed_actions = ["accept", "drop", "reject"]

    state = input_box(screen, f"Enter ct state ({'/'.join(allowed_states)}):")
    if state is None:
        return
    while state not in allowed_states:
        message_box(screen, f"Invalid state: {state}")
        state = input_box(screen, f"Re-enter state ({'/'.join(allowed_states)}):")
        if state is None:
            return

    action = input_box(screen, f"Enter action ({'/'.join(allowed_actions)}):")
    if action is None:
        return
    while action not in allowed_actions:
        message_box(screen, f"Invalid action: {action}")
        action = input_box(screen, f"Re-enter action ({'/'.join(allowed_actions)}):")
        if action is None:
            return

    rule = f"ct state {state} {action}"
    apply_nft_rule(screen, rule, nat=False)

def ip_proto_rule_form(screen):
    src = validate_ip_input_phase2(screen, "Enter source IP:")
    if src is None:
        return
    dst = validate_ip_input_phase2(screen, "Enter destination IP:")
    if dst is None:
        return

    allowed_protocols = ["tcp", "udp"]
    proto = input_box(screen, f"Enter protocol ({'/'.join(allowed_protocols)}):")
    if proto is None:
        return
    while proto not in allowed_protocols:
        message_box(screen, f"Invalid protocol: {proto}")
        proto = input_box(screen, f"Re-enter protocol ({'/'.join(allowed_protocols)}):")
        if proto is None:
            return

    dport = input_box(screen, "Enter destination port (1-65535):")
    if dport is None:
        return
    if not dport.isdigit() or not (1 <= int(dport) <= 65535):
        message_box(screen, f"Invalid port: {dport}")
        return

    allowed_actions = ["accept", "drop", "reject"]
    action = input_box(screen, f"Enter action ({'/'.join(allowed_actions)}):")
    if action is None:
        return
    while action not in allowed_actions:
        message_box(screen, f"Invalid action: {action}")
        action = input_box(screen, f"Re-enter action ({'/'.join(allowed_actions)}):")
        if action is None:
            return

    rule = f"ip saddr {src} ip daddr {dst} {proto} dport {dport} {action}"
    apply_nft_rule(screen, rule, nat=False)

def icmp_rule_form(screen):
    src = validate_ip_input_phase2(screen, "Enter source IP:")
    if src is None:
        return
    dst = validate_ip_input_phase2(screen, "Enter destination IP:")
    if dst is None:
        return

    allowed_types = ["echo-request", "destination-unreachable"]
    icmp_type = input_box(screen, f"Enter ICMP type ({'/'.join(allowed_types)}):")
    if icmp_type is None:
        return
    while icmp_type not in allowed_types:
        message_box(screen, f"Invalid ICMP type: {icmp_type}")
        icmp_type = input_box(screen, f"Re-enter ICMP type ({'/'.join(allowed_types)}):")
        if icmp_type is None:
            return

    allowed_actions = ["accept", "drop"]
    action = input_box(screen, f"Enter action ({'/'.join(allowed_actions)}):")
    if action is None:
        return
    while action not in allowed_actions:
        message_box(screen, f"Invalid action: {action}")
        action = input_box(screen, f"Re-enter action ({'/'.join(allowed_actions)}):")
        if action is None:
            return


    rule = f"ip saddr {src} ip daddr {dst} icmp type {icmp_type} {action}"
    apply_nft_rule(screen, rule, nat=False)

def masquerade_rule_form(screen):
    src = validate_ip_input_phase2(screen, "Enter source IP:")
    if src is None:
        return
    dst = validate_ip_input_phase2(screen, "Enter destination IP:")
    if dst is None:
        return

    rule = f"ip saddr {src} ip daddr {dst} masquerade"
    apply_nft_rule(screen, rule, nat=True)

def dnat_rule_form(screen):
    src = validate_ip_input_phase2(screen, "Enter source IP:")
    if src is None:
        return
    dst = validate_ip_input_phase2(screen, "Enter destination IP:")
    if dst is None:
        return

    dport = input_box(screen, "Enter destination port (1-65535):")
    if dport is None:
        return
    if not dport.isdigit() or not (1 <= int(dport) <= 65535):
        message_box(screen, f"Invalid port: {dport}")
        return

    new_target = input_box(screen, "Enter DNAT target (IP:PORT):")
    if new_target is None:
        return
    if ':' not in new_target:
        message_box(screen, "Invalid DNAT target format (use IP:PORT).")
        return
    ip_part, port_part = new_target.split(':', 1)
    try:
        ipaddress.IPv4Address(ip_part)
    except:
        message_box(screen, f"Invalid IP in DNAT target: {ip_part}")
        return
    if not port_part.isdigit() or not (1 <= int(port_part) <= 65535):
        message_box(screen, f"Invalid port in DNAT target: {port_part}")
        return

    rule = f"ip saddr {src} ip daddr {dst} tcp dport {dport} dnat to {new_target}"
    apply_nft_rule(screen, rule, nat=True)

############################
# Phase 2 TUI Menu         #
############################

def nftables_menu(screen):
    if not check_nft_installed_phase2(screen):
        return  # If installation/enable fails, return quietly

    selected = 0
    options = [
        "Create ct_state rule",
        "Create IP-based rule",
        "Create ICMP rule",
        "Create masquerade rule",
        "Create DNAT rule",
        "Back to Main Menu"
    ]

    while True:
        screen.clear()
        screen.border(0)
        max_y, max_x = screen.getmaxyx()
        print_wrapped(screen, 2, 2, "Phase 2: Nftables Management (ESC to go back)", max_x - 4)
        for idx, opt in enumerate(options):
            prefix = "> " if idx == selected else "  "
            print_wrapped(screen, 4+idx, 2, prefix + opt, max_x - 4)

        key = screen.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(options) - 1:
            selected += 1
        elif key in [10, 13]:
            if selected == 0:
                ct_state_rule_form(screen)
            elif selected == 1:
                ip_proto_rule_form(screen)
            elif selected == 2:
                icmp_rule_form(screen)
            elif selected == 3:
                masquerade_rule_form(screen)
            elif selected == 4:
                dnat_rule_form(screen)
            elif selected == 5:
                break
        elif key == 27:
            break

############################
# Main Menu (Phase 1 & 2)  #
############################

def main_menu(screen):
    selected = 0
    options = [
        "Network Configuration ",
        "Nftables Management ",
        "Open vSwitch Management ",
        "Network Monitoring ",
        "Exit"
    ]
    while True:
        screen.clear()
        screen.border(0)
        max_y, max_x = screen.getmaxyx()
        print_wrapped(screen, 2, 2, "Main Menu (ESC to exit)", max_x - 4)
        for idx, opt in enumerate(options):
            prefix = "> " if idx == selected else "  "
            print_wrapped(screen, 4+idx, 2, prefix + opt, max_x - 4)

        key = screen.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(options) - 1:
            selected += 1
        elif key in [10, 13]:
            if selected == 0:
                network_configuration_menu(screen)
            elif selected == 1:
                nftables_menu(screen)
            elif selected == 2:
                message_box(screen, "Phase 3: OVS Management - Not Implemented")
            elif selected == 3:
                message_box(screen, "Phase 4: Network Monitoring - Not Implemented")
            elif selected == 4:
                break
        elif key == 27:
            break

def main(screen):
    if os.geteuid() != 0:
        screen.clear()
        screen.border(0)
        message_box(screen, "Error: Must run as root.\nPress any key to exit.")
        return
    main_menu(screen)

if __name__ == '__main__':
    curses.wrapper(main)