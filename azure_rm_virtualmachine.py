#!/usr/bin/python
#
# (c) 2016 Matt Davis, <mdavis@redhat.com>
#          Chris Houseknecht, <chouseknecht@redhat.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

DOCUMENTATION = '''
---
module: azure_rm_virtualmachine
'''

RETURNS = '''
{
    "changed": true,
    "check_mode": false,
    "results": {
        "id": "/subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/Testing/providers/Microsoft.Compute/virtualMachines/testvm002",
        "location": "eastus",
        "name": "testvm002",
        "properties": {
            "hardwareProfile": {
                "vmSize": "Standard_D1"
            },
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/Testing/providers/Microsoft.Network/networkInterfaces/testvm001"
                    }
                ]
            },
            "osProfile": {
                "adminUsername": "chouseknecht",
                "computerName": "testvm",
                "linuxConfiguration": {
                    "disablePasswordAuthentication": false
                },
                "secrets": []
            },
            "provisioningState": "Succeeded",
            "storageProfile": {
                "dataDisks": [],
                "imageReference": {
                    "offer": "CentOS",
                    "publisher": "OpenLogic",
                    "sku": "7.1",
                    "version": "7.1.20160308"
                },
                "osDisk": {
                    "caching": "ReadOnly",
                    "createOption": "fromImage",
                    "name": "testvm001.vsd",
                    "osType": "Linux",
                    "vhd": {
                        "uri": "https://testaccount001.blob.core.windows.net/testvm001/testvm001.vsd.vhd"
                    }
                }
            }
        },
        "type": "Microsoft.Compute/virtualMachines"
    }
}

'''


import re
from collections import namedtuple
import sys
# normally we'd put this at the bottom to preserve line numbers, but we can't use a forward-defined base class
# without playing games with __metaclass__ or runtime base type hackery.
# TODO: figure out a better way...
from ansible.module_utils.basic import *
from ansible.module_utils.azure_rm_common import *

try:
    from msrestazure.azure_exceptions import CloudError
    from azure.common import AzureMissingResourceHttpError
    from azure.mgmt.compute.models import NetworkInterfaceReference, VirtualMachine, HardwareProfile,\
        StorageProfile, OSProfile, OSDisk, VirtualHardDisk, ImageReference, NetworkProfile
    from azure.mgmt.compute.models.compute_management_client_enums import CachingTypes, DiskCreateOptionTypes, \
        VirtualMachineSizeTypes
except ImportError:
    # This is handled in azure_rm_common
    pass


AZURE_OBJECT_CLASS = 'VirtualMachine'


def extract_names_from_blob_uri(self, blob_uri):
    # HACK: ditch this once python SDK supports get by URI
    m = re.match('^https://(?P<accountname>[^\.]+)\.blob\.core\.windows\.net/(?P<containername>[^/]+)/(?P<blobname>.+)$', blob_uri)
    if not m:
        raise Exception("unable to parse blob uri '%s'" % blob_uri)
    extracted_names = m.groupdict()
    return extracted_names


class AzureRMVirtualMachine(AzureRMModuleBase):   

    def __init__(self, **kwargs):

        self.module_arg_spec = dict(
            resource_group=dict(type='str', required=True),
            name=dict(type='str', required=True),
            state=dict(choices=['stopped','started', 'absent'], default='started', type='str'),
            location=dict(type='str'),
            short_hostname=dict(type='str'),
            vm_size=dict(type='str', choices=[], default='Standard_D1'),
            force=dict(type='bool', default=False),
            admin_username=dict(type='str'),
            admin_password=dict(type='str', ),
            ssh_password=dict(type='bool', default=True),
            ssh_public_key=dict(type='str'),
            image_publisher=dict(type='str'),
            image_offer=dict(type='str'),
            image_sku=dict(type='str'),
            image_version=dict(type='str', default='latest'),
            storage_account_name=dict(type='str', aliases=['storage_account']),
            storage_container_name=dict(type='str', aliases=['storage_container'], default='vhds'),
            storage_blob_name=dict(type='str', aliases=['storage_blob']),
            os_disk_caching=dict(type='str', aliases=['disk_caching'], choices=['ReadOnly', 'ReadWrite'],
                                 default='ReadOnly'),
            os_type=dict(type='str', choices=['linux', 'windows'], default='linux'),
            network_interface_names=dict(type='list', aliases=['network_interfaces']),
            delete_network_interfaces=dict(type='bool', default=False, aliases=['delete_nics']),
            delete_virtual_storage=dict(type='bool', default=False, aliases=['delete_vhds']),
            delete_public_ips=dict(type='bool', default=False),
            tags=dict(type='dict'),
            log_path=dict(type='str', default='azure_rm_virtualmachine.log'),
        )

        required_if = [
            ('state', 'started', ['image_publisher', 'image_offer', 'image_sku',
                                  'image_version', 'storage_account_name',
                                  'storage_container_name', 'storage_blob_name',
                                  'network_interface_names', 'network_interface_names',
                                  'admin_username']
             ),
        ]

        for key in VirtualMachineSizeTypes:
            self.module_arg_spec['vm_size']['choices'].append(getattr(key, 'value'))

        super(AzureRMVirtualMachine, self).__init__(derived_arg_spec=self.module_arg_spec,
                                                    required_if=required_if,
                                                    supports_check_mode=True,
                                                    **kwargs)

        self.resource_group = None
        self.name = None
        self.state = None
        self.location = None
        self.short_hostname = None
        self.vm_size = None
        self.admin_username = None
        self.admin_password = None
        self.ssh_password = None
        self.ssh_public_key = None
        self.image_publisher = None
        self.image_offer = None
        self.image_sku = None
        self.image_version = None
        self.storage_account_name = None
        self.storage_container_name = None
        self.storage_blob_name = None
        self.os_type = None
        self.os_disk_caching = None
        self.network_interface_names = None
        self.delete_network_interfaces = None
        self.delete_virtual_storage = None
        self.delete_public_ips = None
        self.tags = None
        self.force = None

        self.results = dict(
            changed=False,
            check_mode=self.check_mode,
            results={}
        )

    def exec_module_impl(self, **kwargs):

        for key in self.module_arg_spec:
            setattr(self, key, kwargs[key])

        changed = False
        results = dict()
        vm = None
        network_interfaces = []

        resource_group = self.get_resource_group(self.resource_group)
        if not self.location:
            # Set default location
            self.location = resource_group.location

        if self.state == 'started':
            # Verify parameters and resolve any defaults
            self.vm_size_is_valid()

            for name in self.network_interface_names:
                nic = self.get_network_interface(name)
                network_interfaces.append(NetworkInterfaceReference(id=nic.id))

            if not self.storage_blob_name:
                self.storage_blob_name = self.name + '.vsd'

            image_version = self.get_image_version()
            if not image_version:
                self.fail("Error could not find image {0} {1} {2} {3}".format(self.image_publisher,
                                                                              self.image_offer,
                                                                              self.image_sku,
                                                                              self.image_version))
            if self.image_version == 'latest':
                self.image_version = image_version.name
                self.log("Using image version {0}".format(self.image_version))

            self.get_storage_account()

        try:
            self.log("Fetching virtual machine {0}".format(self.name))
            vm = self.compute_client.virtual_machines.get(self.resource_group, self.name)
            self.check_provisioning_state(vm)

            self.log('Virtual machine {0} exists'.format(self.name))
            vm_dict = self.serialize_obj(vm, AZURE_OBJECT_CLASS)
            self.log(vm_dict, pretty_print=True)

            if self.state == 'started' and self.force:
                self.log('CHANGED: virtual machine {0} exists and forced option set.'.format(self.name))
                changed = True
            elif self.state == 'started':
                self.log('validating vm attributes against args...')
                # TODO: validate attributes (name, tags, what else?)
            elif self.state == 'stopped':
                pass
            elif self.state == 'absent':
                self.log("CHANGED: virtual machine {0} exists and requested state is 'absent'".format(self.name))
                changed = True # we should hit the exception handler below if the vm doesn't exist, so we know it does
        except CloudError:
            self.log('Virtual machine {0} does not exist'.format(self.name))
            if self.state == 'started':
                self.log("CHANGED: virtual machine does not exist but state is 'present'".format(self.name))
                changed = True

        self.results['changed'] = changed
        self.results['results'] = results

        if self.check_mode:
            return self.results

        if changed:
            if self.state == 'started' and self.force:
                # Remove existing VM
                self.delete_vm()
                vm = None

            if self.state == 'started':
                if not vm:
                    # Create the VM
                    self.log("Create virtual machine {0}".format(self.name))

                    # TODO: add this back in once we're ready to create a default nic
                    # # ensure nic/pip exist
                    # try:
                    #     log('fetching nic...')
                    #     nic_resp = network_client.network_interfaces.get(resource_group, network.get('virtual_nic_name'))
                    #     nic_id = nic_resp.network_interface.id
                    # except AzureMissingResourceHttpError:
                    #     log('nic does not exist...')
                    #     # TODO: create nic
                    #     raise Exception('nic does not exist')

                    vhd = VirtualHardDisk(uri='https://{0}.blob.core.windows.net/{1}/{2}.vhd'.format(
                        self.storage_account_name,
                        self.storage_container_name,
                        self.storage_blob_name,
                    ))

                    # vm_size = None
                    # for key in VirtualMachineSizeTypes:
                    #     if key.value == self.vm_size:
                    #         vm_size = key

                    vm_resource = VirtualMachine(
                        location=self.location,
                        name=self.name,
                        tags=self.tags,
                        os_profile=OSProfile(
                            admin_username=self.admin_username,
                            admin_password=self.admin_password,
                            computer_name=self.short_hostname,
                        ),
                        hardware_profile=HardwareProfile(
                            vm_size=self.vm_size
                        ),
                        storage_profile=StorageProfile(
                            os_disk=OSDisk(
                                self.storage_blob_name,
                                vhd,
                                DiskCreateOptionTypes.from_image,
                                caching=self.os_disk_caching,
                            ),
                            image_reference=ImageReference(
                                publisher=self.image_publisher,
                                offer=self.image_offer,
                                sku=self.image_sku,
                                version=self.image_version,
                            ),
                        ),
                        network_profile=NetworkProfile(
                            network_interfaces=network_interfaces
                        ),
                    )
                    self.log("Creating virtual machine with parameters:")
                    vm_dict = self.serialize_obj(vm_resource, 'VirtualMachine')
                    self.log(vm_dict, pretty_print=True)
                    self.results['results'] = self.create_vm(vm_resource)

                    #
                    # # TODO: reuse this code section for check mode
                    #
                    # for nic_ref in vm.network_profile.network_interfaces:
                    #     nic_values = self._extract_names_from_uri_id(nic_ref.reference_uri)
                    #     nic_resp = self.network_client.network_interfaces.get(nic_values.get('rg_name'), nic_values.get('name'))
                    #     nic = nic_resp.network_interface
                    #     is_primary = nic.primary
                    #     # TODO: can there be more than one?
                    #
                    #     if is_primary:
                    #         ip_cfg = nic.ip_configurations[0]
                    #         result['primary_private_ip'] = ip_cfg.private_ip_address
                    #         public_ip_ref = ip_cfg.public_ip_address
                    #         if public_ip_ref: # look up the public ip object to get the address
                    #             pip_values = self._extract_names_from_uri_id(public_ip_ref.id)
                    #             pip_resp = self.network_client.public_ip_addresses.get(pip_values.get('rg_name'), pip_values.get('name'))
                    #             result['primary_public_ip'] = pip_resp.public_ip_address.ip_address

        return self.results

    def delete_vm(self):
        vhd_uris = []
        nic_names = []
        pip_names = []

        if self.delete_virtual_storage:
            # store the attached vhd info so we can nuke it after the VM is gone
            self.log('Storing VHD URI for deletion')
            vhd_uris.append(vm.storage_profile.os_disk.virtual_hard_disk.uri)
            self.log("VHD URIs to delete: {0}".format(', '.join(vhd_uris)))
            self.results['deleted_vhd_uris'] = vhd_uris

            # TODO: add support for deleting data disk vhds

        if self.delete_network_interfaces:
            # store the attached nic info so we can nuke them after the VM is gone
            self.log('Storing NIC names for deletion.')
            for interface_id in vm.network_profile.network_interfaces:
                id_dict = azure_id_to_dict(interface_id)
                nic_names.append(id_dict['networkInterfaces'])
            self.log('NIC names to delete {0}'.format(', '.join(nic_names)))
            self.results['deleted_network_interfaces'] = nic_names
            if self.delete_public_ips:
                # also store each nic's attached public IPs and delete after the NIC is gone
                for name in nic_names:
                    nic = self.get_network_interface(name)
                    for ipc in nic.ip_configurations:
                        if ipc.public_ip_address:
                            pip_dict = azure_id_to_dict(ipc.public_ip_address.id)
                            pip_names.append(pip_dict['publicIPAddresses'])
                self.log('Public IPs to  delete are {0}'.format(', '.join(pip_names)))
                self.results['deleted_public_ips'] = pip_names

        try:
            self.compute_client.virtual_machines.delete(self.resource_group, self.name)
        except Exception, exc:
            self.fail("Error deleting virtual machine {0} - {1}".format(self.name, str(exc)))

        # TODO: parallelize nic, vhd, and public ip deletions with begin_deleting
        # TODO: best-effort to keep deleting other linked resources if we encounter an error
        if self.delete_virtual_storage:
            self.log('Deleting virtual storage')
            self.delete_virtual_storage(vhd_uris)

        if self.delete_network_interfaces:
            self.log('Deleting network interfaces')
            for name in nic_names:
                self.delete_nic(name)

        if self.delete_public_ips:
            self.log('Deleting public IPs')
            for name in pip_names:
                self.delete_pip(name)
        return True

    def get_network_interface(self, name):
        try:
            nic = self.network_client.network_interfaces.get(self.resource_group, name)
            return nic
        except Exception, exc:
            self.fail("Error fetching network interface {0} - {1}".format(name, str(exc)))

    def delete_nic(self, name):
        self.log("Deleting network interface {0}".format(name))
        try:
            poller = self.network_client.network_interfaces.delete(self.resource_group, name)
        except Exception, exc:
            self.fail("Error deleting network interface {0} - {1}".format(name, str(exc)))
        self.get_poller_result(poller)
        # Delete doesn't return anything. If we get this far, assume success
        return True

    def delete_pip(self, name):
        try:
            poller = self.network_client.public_ip_addresses.delete(self.resource_group, name)
        except Exception, exc:
            self.fail("Error deleting {0} - {1}".format(name, str(exc)))
        self.get_poller_result(poller)
        # Delete returns nada. If we get here, assume that all is well.
        return True

    def delete_virtual_storage(self, vhd_uris):
        for uri in vhd_uris:
            self.log("Extracting info from blob uri '{0}'".format(uri))
            blob_parts = extract_names_from_blob_uri(uri)
            storage_account_name = blob_parts['accountname']
            container_name = blob_parts['containername']
            blob_name = blob_parts['blobname']

            blob_client = self.get_blob_client(self.resource_group, storage_account_name)

            self.log("Delete blob {0}:{1}".format(container_name, blob_name))
            try:
                blob_client.delete_blob(container_name, blob_name)
            except Exception, exc:
                self.fail("Error deleting blob {0}:{1} - {2}".format(container_name, blob_name, str(exc)))

    def get_image_version(self):
        try:
            versions = self.compute_client.virtual_machine_images.list(self.location,
                                                                       self.image_publisher,
                                                                       self.image_offer,
                                                                       self.image_sku)
        except Exception, exc:
            self.fail("Error fetching image {0} {1} {2} - {4}".format(self.image_publisher,
                                                                      self.image_offer,
                                                                      self.image_sku,
                                                                      str(exc)))
        if versions and len(versions) > 0:
            if self.image_version == 'latest':
                return versions[len(versions) - 1]
            for version in versions:
                if version.name == self.image_version:
                    return version
        return None

    def get_storage_account(self):
        try:
            account = self.storage_client.storage_accounts.get_properties(self.resource_group,
                                                                          self.storage_account_name)
            return account
        except Exception, exc:
            self.fail("Error fetching storage account {0} - {1}".format(self.storage_account_name, str(exc)))

    def create_vm(self, params):
        try:
            poller = self.compute_client.virtual_machines.create_or_update(self.resource_group, self.name, params)
        except Exception, exc:
            self.fail("Error creating or updating virtual machine {0} - {1}".format(self.name, str(exc)))
        vm = self.get_poller_result(poller)
        return self.serialize_obj(vm, AZURE_OBJECT_CLASS)

    def vm_size_is_valid(self):
        '''
        Validate self.vm_size against the list of virtual machine sizes available for the account and location.
        :return: list of available sizes
        '''
        try:
            sizes = self.compute_client.virtual_machine_sizes.list(self.location)
        except Exception, exc:
            self.fail("Error retrieving available machine sizes - {0}".format(str(exc)))
        for size in sizes:
            if size.name == self.vm_size:
                return True
        return False

    def create_default_storage_account(self):
        pass

    def create_default_virtual_network(self):
        pass

    def create_default_subnet(self):
        pass

    def create_default_nic(self):
        pass

def main():
    # standalone debug setup
    if '--interactive' in sys.argv:
        # early import the module and reset the complex args
        import ansible.module_utils.basic

        ansible.module_utils.basic.MODULE_COMPLEX_ARGS = json.dumps(dict(
            resource_group='rm_demo',
            name='mdavis-test1-vm',
            state='present',
            location='West US',
            short_hostname='mdavis-test1-vm',
            vm_size='Standard_A1',
            admin_username='mdavis',
            admin_password='R00tpassword#',
            image_publisher='MicrosoftWindowsServer',
            image_offer='WindowsServer',
            image_sku='2012-R2-Datacenter',
            image_version='4.0.20151214',
            os_disk_storage_account_name='test',
            os_disk_storage_container_name='vhds',
            os_disk_storage_blob_name='mdavis-test1-vm',
            os_type='windows',
            delete_nics=True,
            delete_vhds=True,
            delete_public_ips=True,
            nic_ids=['/subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/rm_demo/providers/Microsoft.Network/networkInterfaces/test-nic'],
            log_mode="stderr"
        ))

    AzureRMVirtualMachine().exec_module()

main()

