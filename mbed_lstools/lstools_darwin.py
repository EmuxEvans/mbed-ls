"""
mbed SDK
Copyright (c) 2011-2015 ARM Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import re
import subprocess
import plistlib

from lstools_base import MbedLsToolsBase

class MbedLsToolsDarwin(MbedLsToolsBase):
    """ MbedLsToolsDarwin supports mbed-enabled platforms detection on Mac OS X
    """

    mbed_volume_name_match = re.compile(r'\bmbed\b', re.I)

    def list_mbeds(self):
        """ returns mbed list with platform names if possible
        """
        
        result = []
        
        # {volume_id: {serial:, vendor_id:, product_id:, tty:}}
        volumes = self.get_mbed_volumes()
        #print 'volumes:', volumes
        
        # {volume_id: mount_point}
        mounts = self.get_mount_points()
        #print "mounts:", mounts

        # put together all of that info into the expected format:
        result =  [
            {
                'mount_point': mounts[v],
                'serial_port': volumes[v]['tty'],
                  'target_id': self.target_id(volumes[v]),
              'platform_name': self.platform_name(self.target_id(volumes[v]))
            } for v in volumes
        ]

        # if we're missing any target ids, try to fill those in by reading
        # mbed.htm:
        for m in result:
            if m['mount_point'] and  not m['target_id']:
                m['target_id'] = self.get_mbed_htm_target_id(m['mount_point'])
        
        # finally fill in any missing platform names:
        for m in result:
            if m['target_id'] and not m['platform_name']:
                tid = m['target_id'][:4]
                m['platform_name'] = self.platform_name(tid)

        return result

    
    def get_mount_points(self):
        ''' Returns map {volume_id: mount_point} '''

        # list disks, this gives us disk name, and volume name + mount point:
        diskutil_ls = subprocess.Popen(['diskutil', 'list', '-plist'], stdout=subprocess.PIPE)
        disks = plistlib.readPlist(diskutil_ls.stdout)
        diskutil_ls.wait()
        
        r = {}

        for disk in disks['AllDisksAndPartitions']:
            mount_point = None
            if 'MountPoint' in disk:
                mount_point = disk['MountPoint']
            r[disk['DeviceIdentifier']] = mount_point
        
        return r

    def get_mbed_volumes(self):
        ''' returns a map {volume_id: {serial:, vendor_id:, product_id:}''' 

        # to find all the possible mbed volumes, we look for registry entries
        # under the USB bus which have a "BSD Name" that starts with "disk"
        # (i.e. this is a USB disk), and have a IORegistryEntryName that
        # matches /\cmbed/
        # ioreg -a -r -n "AppleUSBXHCI" -l
        ioreg_usb = subprocess.Popen(['ioreg', '-a', '-r', '-n', 'AppleUSBXHCI', '-l'], stdout=subprocess.PIPE)
        usb_bus = plistlib.readPlist(ioreg_usb.stdout)
        ioreg_usb.wait()

        r = {}
        
        def findTTYRecursive(obj):
            ''' return the first tty (AKA IODialinDevice) that we can find in the
                children of the specified object, or None if no tty is present.
            '''
            if 'IODialinDevice' in obj:
                return obj['IODialinDevice']
            if 'IORegistryEntryChildren' in obj:
                for child in obj['IORegistryEntryChildren']:
                    found = findTTYRecursive(child)
                    if found:
                        return found
            return None

        def findVolumesRecursive(obj, parents):
            if 'BSD Name' in obj and obj['BSD Name'].startswith('disk') and \
                    self.mbed_volume_name_match.search(obj['IORegistryEntryName']):
                disk_id = obj['BSD Name']
                # now search up through our parents until we find a serial number:
                usb_info = {
                        'serial':None,
                     'vendor_id':None,
                    'product_id':None,
                           'tty':None,
                }
                for parent in [obj] + parents:
                    if 'USB Serial Number' in parent:
                        usb_info['serial'] = parent['USB Serial Number']
                    if 'idVendor' in parent and 'idProduct' in parent:
                        usb_info['vendor_id'] = parent['idVendor']
                        usb_info['product_id'] = parent['idProduct']
                    if usb_info['serial']:
                        # stop at the first one we find (or we'll pick up hubs,
                        # etc.), but first check for a tty that's also a child of
                        # this device:
                        usb_info['tty'] = findTTYRecursive(parent)
                        break
                r[disk_id] = usb_info
            if 'IORegistryEntryChildren' in obj:
                for child in obj['IORegistryEntryChildren']:
                    findVolumesRecursive(child, [obj] + parents)

        for obj in usb_bus:
            findVolumesRecursive(obj, [])

        return r


    def target_id(self, usb_info):
        if usb_info['serial'] is not None:
            return usb_info['serial']
        else:
            return None

    def platform_name(self, target_id):
        if target_id in self.manufacture_ids:
            return self.manufacture_ids[target_id[:4]]


