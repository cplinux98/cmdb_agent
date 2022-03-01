#!/usr/bin/python3
import os
import json
import logging
import time
import requests

logging.basicConfig(level=logging.INFO,
                    filename='/opt/agent.log',
                    filemode='a',
                    format='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')

class HwInfo():
    def __init__(self):
        self.vm_tag = 0 if os.popen('systemd-detect-virt').read().strip() == "none" else 1
        source = json.loads(os.popen('lshw -c cpu -c memory -c network -c disk -c storage -json').read())
        self.cpu_source = []
        self.mem_source = []
        self.network_source = []
        self.disk_source = json.loads(os.popen('lshw -c disk -json').read())
        self.store_source = []
        for i in source:
            _id = i.get("id")
            class_name = i.get("class")
            desc = i.get("description")
            children = i.get("children")
            if class_name == "processor":
                self.cpu_source.append(i)
            elif class_name == "memory" and desc == "System Memory":
                self.mem_source.append(i)
            elif class_name == "network":
                self.network_source.append(i)
            elif class_name == "storage" and (_id == "raid" or _id == "sata"):
                self.store_source.append(i)
            else:
                continue

    @classmethod
    def b_to_G(cls, num):
        if num == "Unknown":
            return num
        bytes_ = int(num)
        GB = 1 << 30
        return "{} GB".format(bytes_ // GB)

    def cpu_list(self, only_model=False):
        """ [{"num": num, "model": model, "core": core}] """
        ret_list = []
        if only_model:
            return os.popen("""lscpu | grep "Model name"| cut -d":" -f2 | tr -s ' '""").read().strip()
        _list = self.cpu_source
        for i in range(len(_list)):
            _dict = _list[i]
            model = _dict.get("product")
            if not model:
                continue
            slot = _dict.get("slot")
            core = _dict.get("configuration").get("cores")
            ret_list.append({"slot": slot, "model": model, "core": core})
        return ret_list

    def mem_dict(self):
        _list= self.mem_source
        for i in range(len(_list)):
            if _list[i].get('description') == "System Memory":
                return _list[i]

    def mem_total(self):
        mem_total_bytes = self.mem_dict().get('size')
        return self.b_to_G(mem_total_bytes)

    def mem_list(self):
        if self.vm_tag:
            return [{"slot": "Unknown", "size": self.mem_total(), "description": "The virtual machine"}]
        ret_list = []
        _list: list = self.mem_dict().get('children')
        for i in range(len(_list)):
            _dict = _list[i]
            slot = _dict.get("slot", "Unknown")
            size = _dict.get("size", "Unknown")
            description = _dict.get("description")
            ret_list.append({"slot": slot, "size": self.b_to_G(size), "description": description})
        return ret_list

    def net_list(self):
        ret_list = []
        _list = self.network_source
        for i in range(len(_list)):
            _dict = _list[i]
            name = _dict.get('logicalname')
            mac = _dict.get('serial')
            product = _dict.get('product')
            description = _dict.get('description')
            ret_list.append({"name": name, "mac": mac, "product": product, "description": description})
        return ret_list

    def disk_list(self):
        ret_list = []
        _list = self.disk_source
        for i in range(len(_list)):
            _dict = _list[i]
            type = _dict.get('id')
            product = _dict.get('product')
            vendor = _dict.get('vendor')
            size = _dict.get('size', "Unknown")
            ret_list.append({"type": type, "product": product, "vendor": vendor, "size": self.b_to_G(size)})
        return ret_list

    def store_list(self):
        if self.vm_tag:
            return [{"type": "Unknown", "product": "Unknown", "vendor": "Unknown", "description": "The virtual machine"}]
        ret_list = []
        _list = self.store_source
        for i in range(len(_list)):
            _dict = _list[i]
            type = _dict.get('id')
            product = _dict.get('product')
            vendor = _dict.get('vendor')
            description = _dict.get('description')
            ret_list.append({"type": type, "product": product, "vendor": vendor, "description": description})
        return ret_list


    def boot_mac(self):
        return os.popen("cat /sys/class/net/eth0/address").read().strip()

    def boot_ip(self):
        return os.popen("ip addr show eth0 | awk '/inet / {print $2}' | cut -d '/' -f1").read().strip()

    def product(self):
        with open('/sys/devices/virtual/dmi/id/product_name') as fd:
            return fd.read().strip()

    def vendor(self):
        with open('/sys/devices/virtual/dmi/id/sys_vendor') as fd:
            return fd.read().strip()

    def serial(self):
        if self.vm_tag:
            return self.boot_mac().replace(':', '', 5)
        else:
            with open('/sys/devices/virtual/dmi/id/chassis_serial') as fd:
                return fd.read().strip()

    def bmc(self, only_ip=False):
        if self.vm_tag and not only_ip:
            return [{"ipaddr": "Unknown", "mask": "Unknown", "gateway": "Unknown", "mac": "Unknown"}]
        content = {
            "IP Address": "ipaddr",
            "Subnet Mask": "mask",
            "MAC Address": "mac",
            "Default Gateway IP": "gateway"
        }
        ret_dict = dict()
        if os.path.exists("/dev/ipmi0"):
            save_to_file = os.popen('ipmitool lan print > /mnt/ipmi').read()
            with open('/mnt/ipmi') as fd:
                for line in fd.readlines():
                    data = line.split(":", 1)
                    key = data[0].strip()
                    value = data[1].strip().split(' ')[0]
                    if key in content.keys():
                        ret_dict[content.get(key)] = value
        if only_ip:
            return "0.0.0.0" if self.vm_tag else ret_dict.get("ipaddr")
        return [ret_dict]
