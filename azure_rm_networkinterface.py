#!/usr/bin/python
#
# (c) 2016 Matt Davis, <mdavis@redhat.com>
#          Chris Houseknecht, <house@redhat.com>
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

# normally we'd put this at the bottom to preserve line numbers, but we can't use a forward-defined base class
# without playing games with __metaclass__ or runtime base type hackery.
# TODO: figure out a better way...
from ansible.module_utils.basic import *
from ansible.module_utils.azure_rm_common import *

try:
    from msrestazure.azure_exceptions import CloudError
    from azure.common import AzureMissingResourceHttpError
    from azure.mgmt.network.models import NetworkInterface, NetworkInterfaceIPConfiguration, Subnet, \
                                          PublicIPAddress, NetworkSecurityGroup
    from azure.mgmt.network.models.network_management_client_enums import IPAllocationMethod
except ImportError:
    # This is handled in azure_rm_common
    pass


DOCUMENTATION = '''
---
module: azure_rm_networkinterface

short_description: Manage Azure network interfaces.

description:
    - Create, update and delete a network interface. When creating a network interface provide the name of an
      existing virtual network, the name of an existing subnet within the virtual network and the name
      of an existing security group. Optionally specify a private IPv4 address, private IP allocation method,
      and the name of an existing public IP address.
    - For authentication with Azure you can pass parameters, set environment variables or use a profile stored
      in ~/.azure/credentials. Authentication is possible using a service principal or Active Directory user.
    - To authenticate via service principal pass subscription_id, client_id, secret and tenant or set set environment
      variables AZURE_SUBSCRIPTION_ID, AZURE_CLIENT_ID, AZURE_SECRET and AZURE_TENANT.
    - To Authentication via Active Directory user pass ad_user and password, or set AZURE_AD_USER and
      AZURE_PASSWORD in the environment.
    - Alternatively, credentials can be stored in ~/.azure/credentials. This is an ini file containing
      a [default] section and the following keys: subscription_id, client_id, secret and tenant or
      ad_user and password. It is also possible to add addition profiles to this file. Specify the profile
      by passing profile or setting AZURE_PROFILE in the environment.

options:
    profile:
        description:
            - security profile found in ~/.azure/credentials file
        required: false
        default: null
    subscription_id:
        description:
            - Azure subscription Id that owns the resource group and storage accounts.
        required: false
        default: null
    client_id:
        description:
            - Azure client_id used for authentication.
        required: false
        default: null
    secret:
        description:
            - Azure client_secrent used for authentication.
        required: false
        default: null
    tenant:
        description:
            - Azure tenant_id used for authentication.
        required: false
        default: null
    resource_group:
        description:
            - Name of a resource group.
        required: true
        default: null
    name:
        description:
            - Name of the network interface.
        default: null
    state:
        description:
            - Assert the state of the network interface. Use 'present' to create or update an interface and
              'absent' to delete an interface.
        required: false
        default: present
        choices:
            - absent
            - present
    location:
        description:
            - Valid azure location. Defaults to location of the resource group.
        default: resource_group location
    private_ip_address:
        description:
            - Valid IPv4 address that falls within the specified subnet.
        default: null
    private_ip_allocation_method:
        description:
            - Specify whether or not the assigned IP address is permanent.
        default: Dynamic
        choices:
            - Dynamic
            - Static
    public_ip_address_name:
        description:
            - Name of an existing public IP address object to associate with the security group.
        default: null
    security_group_name:
        description:
            - Name of an existing security group with which to associate the network interface. Required when
              state is 'present'. Cannot be changed after network interface is required.
        default: null
        required: true
        aliases:
            - security_group
    subnet_name:
        description:
            - Name of an existing subnet within the specified virtual network. Required when state is 'present'.
              Cannot be changed after network interface is required.
        required: true
        default: null
        aliases:
            - subnet
    tags:
        description:
            - Dictionary of string:string pairs to assign as metadata to the object. Treated as the explicit metadata
              for the object. In other words, existing metadata will be replaced with provided values. If no values
              provided, existing metadata will be removed.
        required: false
        default: null
    virtual_network_name:
        desription:
            - Name of an existing virtual network with which the network interface will be associated. Required
              when state is 'present'. Cannot be changed after network interface is required.
        default: null
        required true
        aliases:
            - virtual_network
requirements:
    - "python >= 2.7"
    - "azure >= 2.0.0"

authors:
    - "Chris Houseknecht house@redhat.com"
    - "Matt Davis mdavis@redhat.com"
'''

EXAMPLES = '''
    - name: Create nic
        azure_rm_networkinterface:
            name: nic003
            resource_group: "{{ resource_group }}"
            virtual_network_name: vnet001
            subnet_name: subnet001
            security_group_name: secgroup001
            public_ip_address_name: publicip001

    - name: Delete network interface
        azure_rm_networkinterface:
            name: nic003
            state: absent
            resource_group: "{{ resource_group }}"
'''

RETURNS = '''
{
    "changed": true,
    "check_mode": false,
    "results": {
        "dns_settings": {
            "applied_dns_servers": [],
            "dns_servers": [],
            "internal_dns_name_label": null,
            "internal_fqdn": null
        },
        "enable_ip_forwarding": false,
        "etag": "W/\"be115a43-2148-4545-a324-f33ad444c926\"",
        "id": "/subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/Testing/providers/Microsoft.Network/networkInterfaces/nic003",
        "ip_configuration": {
            "name": "default",
            "private_ip_address": "10.1.0.10",
            "private_ip_allocation_method": "Static",
            "public_ip_address": {
                "id": "/subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/Testing/providers/Microsoft.Network/publicIPAddresses/publicip001",
                "name": "publicip001"
            },
            "subnet": {}
        },
        "location": "eastus2",
        "mac_address": null,
        "name": "nic003",
        "network_security_group": {},
        "primary": null,
        "provisioning_state": "Succeeded",
        "tags": null,
        "type": "Microsoft.Network/networkInterfaces"
    }
}
'''

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,61}[a-z0-9]$")


def nic_to_dict(nic):
    result = dict(
        id=nic.id,
        name=nic.name,
        type=nic.type,
        location=nic.location,
        tags=nic.tags,
        network_security_group=dict(),
        ip_configuration=dict(
            name=nic.ip_configurations[0].name,
            private_ip_address=nic.ip_configurations[0].private_ip_address,
            private_ip_allocation_method=nic.ip_configurations[0].private_ip_allocation_method.value,
            subnet=dict(),
            public_ip_address=dict(),
        ),
        dns_settings=dict(
            dns_servers=nic.dns_settings.dns_servers,
            applied_dns_servers=nic.dns_settings.applied_dns_servers,
            internal_dns_name_label=nic.dns_settings.internal_dns_name_label,
            internal_fqdn=nic.dns_settings.internal_fqdn
        ),
        mac_address=nic.mac_address,
        primary=nic.primary,
        enable_ip_forwarding=nic.enable_ip_forwarding,
        provisioning_state=nic.provisioning_state,
        etag=nic.etag,
    )

    if nic.network_security_group:
        result['network_security_group']['id'] = nic.network_security_group.id
        result['network_security_group']['name'] = nic.network_security_group.name

    if nic.ip_configurations[0].subnet:
        result['ip_configuration']['subnet']['id'] = \
            nic.ip_configurations[0].subnet.id
        result['ip_configuration']['subnet']['id'] = \
            nic.ip_configurations[0].subnet.name

    if nic.ip_configurations[0].public_ip_address:
        result['ip_configuration']['public_ip_address']['id'] = \
            nic.ip_configurations[0].public_ip_address.id
        id_keys = azure_id_to_dict(nic.ip_configurations[0].public_ip_address.id)
        result['ip_configuration']['public_ip_address']['name'] = id_keys['publicIPAddresses']

    return result


class AzureRMNetworkInterface(AzureRMModuleBase):

    def __init__(self, **kwargs):

        self.module_arg_spec = dict(
            resource_group=dict(required=True),
            name=dict(required=True),
            location=dict(type='str'),
            security_group_name=dict(type='str', aliases=['security_group']),
            state=dict(default='present', choices=['present', 'absent']),
            private_ip_address=dict(type='str'),
            private_ip_allocation_method=dict(type='str', choices=['Dynamic', 'Static'], default='Dynamic'),
            public_ip_address_name=dict(type='str', aliases=['public_ip']),
            subnet_name=dict(type='str', aliases=['subnet']),
            virtual_network_name=dict(type='str', aliases=['virtual_network']),
            tags=dict(type='dict'),
            log_path=dict(type='str', default='azure_rm_networkinterface.log')
        )

        required_if = [
            ('state', 'present', ['subnet_name', 'virtual_network_name', 'security_group_name'])
        ]

        super(AzureRMNetworkInterface, self).__init__(derived_arg_spec=self.module_arg_spec,
                                                      required_if=required_if,
                                                      supports_check_mode=True, **kwargs)

        self.resource_group = None
        self.name = None
        self.location = None
        self.security_group_name = None
        self.private_ip_address = None
        self.private_ip_allocation_method = None
        self.public_ip_address_name = None
        self.state = None
        self.subnet_name = None
        self.tags = None
        self.virtual_network_name = None
        self.security_group_name = None

        self.results = dict(
            changed=False,
            check_mode=self.check_mode,
            results=dict()
        )

    def exec_module_impl(self, **kwargs):

        for key in self.module_arg_spec:
            setattr(self, key, kwargs[key])

        results = dict()
        changed = False
        nic = None

        resource_group = self.get_resource_group(self.resource_group)
        if not self.location:
            # Set default location
            self.location = resource_group.location

        if not NAME_PATTERN.match(self.name):
            self.fail("Parameter error: name must begin with a letter or number, end with a letter or number "
                      "and contain at least one number.")

        if self.state == 'present':
            subnet = self.get_subnet()
            if self.public_ip_address_name:
                public_ip = self.get_public_ip_address(self.public_ip_address_name)
                self.log("public ip")
                self.log(str(public_ip))

            if self.security_group_name:
                nsg = self.get_security_group(self.security_group_name)

        try:
            self.log('Fetching network interface {0}'.format(self.name))
            nic = self.network_client.network_interfaces.get(self.resource_group, self.name)

            self.log('Network interface {0} exists'.format(self.name))
            self.check_provisioning_state(nic)
            results = nic_to_dict(nic)

            if self.state == 'present':
                if self.tags:
                    if results['tags'] != self.tags:
                        self.log("CHANGED: network interface {0} tags".format(self.name))
                        changed = True
                        results['tags'] = self.tags

                if self.private_ip_address:
                    if results['ip_configuration']['private_ip_address'] != self.private_ip_address:
                        self.log("CHANGED: network interface {0} private ip".format(self.name))
                        changed = True
                        results['ip_configuration']['private_ip_address'] = self.private_ip_address

                if self.public_ip_address_name:
                    if results['ip_configuration']['public_ip_address'].get('id') != public_ip.id:
                        self.log("CHANGED: network interface {0} public ip".format(self.name))
                        changed = True
                        results['ip_configuration']['public_ip_address_id'] = public_ip.id
                        results['ip_configuration']['public_ip_address_name'] = public_ip.name

                # The security group (if there is one) is not returned by the API
                # if self.security_group_name:
                #     if results['network_security_group'].get('id') != nsg.id:
                #         self.log("CHANGED: network interface {0} network security group".format(self.name))
                #         changed = True
                #         results['network_security_group']['id'] = nsg.id
                #         results['network_security_group']['name'] = nsg.name

                if results['ip_configuration']['private_ip_allocation_method'] != self.private_ip_allocation_method:
                    self.log("CHANGED: network interface {0} private ip allocation".format(self.name))
                    changed = True
                    results['ip_configuration']['private_ip_allocation_method'] = self.private_ip_allocation_method

                # The subnet value is not returned by the API
                # if results['ip_configuration']['subnet'].get('id') != subnet.id:
                #     changed = True
                #     self.log("CHANGED: network interface {0} subnet".format(self.name))
                #     results['ip_configuration']['subnet']['id'] = subnet.id
                #     results['ip_configuration']['subnet']['name'] = subnet.name

            elif self.state == 'absent':
                self.log("CHANGED: network interface {0} exists but requested state is 'absent'".format(self.name))
                changed = True
        except CloudError:
            self.log('Network interface {0} does not exist'.format(self.name))
            if self.state == 'present':
                self.log("CHANGED: network interface {0} does not exist but requested state is "
                         "'present'".format(self.name))
                changed = True

        self.results['changed'] = changed
        self.results['results'] = results

        if self.check_mode:
            return self.results
    
        if changed:
            if self.state == 'present':
                if not nic:
                    # create network interface
                    self.log("Creating network interface {0}.".format(self.name))

                    nic = NetworkInterface(
                        location=self.location,
                        name=self.name,
                        tags=self.tags,
                        ip_configurations=[
                            NetworkInterfaceIPConfiguration(
                                name='default',
                                private_ip_allocation_method=self.private_ip_allocation_method,
                            )
                        ]
                    )
                    nic.ip_configurations[0].subnet = Subnet(id=subnet.id)
                    if self.security_group_name:
                        nic.network_security_group = NetworkSecurityGroup(id=nsg.id,
                                                                          name=nsg.name,
                                                                          location=nsg.location,
                                                                          resource_guid=nsg.resource_guid)
                    if self.private_ip_address:
                        nic.ip_configurations[0].private_ip_address = self.private_ip_address
                    if self.public_ip_address_name:
                        nic.ip_configurations[0].public_ip_address = PublicIPAddress(
                            id=public_ip.id,
                            name=public_ip.name,
                            location=public_ip.location,
                            resource_guid=public_ip.resource_guid)
                else:
                    self.log("Updating network interface {0}.".format(self.name))
                    nic = NetworkInterface(
                        location=results['location'],
                        name=results['name'],
                        tags=results['tags'],
                        ip_configurations=[
                            NetworkInterfaceIPConfiguration(
                                name=results['ip_configuration']['name'],
                                private_ip_allocation_method=
                                    results['ip_configuration']['private_ip_allocation_method'],
                            )
                        ],
                    )
                    nic.ip_configurations[0].subnet = Subnet(id=subnet.id)
                    if results['ip_configuration'].get('private_ip_address'):
                        nic.ip_configurations[0].private_ip_address = results['ip_configuration']['private_ip_address']
                    if results['ip_configuration']['public_ip_address'].get('id'):
                        public_ip = \
                            self.get_public_ip_address(results['ip_configuration']['public_ip_address']['name'])
                        nic.ip_configurations[0].public_ip_address = PublicIPAddress(
                            id=public_ip.id,
                            name=public_ip.name,
                            location=public_ip.location,
                            resource_guid=public_ip.resource_guid)
                    if results['network_security_group'].get('id'):
                        nsg = self.get_security_group(results['network_security_group']['name'])
                        nic.network_security_group = NetworkSecurityGroup(id=nsg.id,
                                                                          name=nsg.name,
                                                                          location=nsg.location,
                                                                          resource_guid=nsg.resource_guid)

                # See what actually gets sent to the API
                serializer = Serializer()
                request_body = serializer.body(nic, 'NetworkInterface')
                self.log(request_body, pretty_print=True)

                self.results['results'] = self.create_or_update_nic(nic)

            elif self.state == 'absent':
                self.log('Deleting network interface {0}'.format(self.name))
                self.delete_nic()
    
        return self.results

    def create_or_update_nic(self, nic):
        try:
            poller = self.network_client.network_interfaces.create_or_update(self.resource_group, self.name, nic)
        except Exception, exc:
            self.fail("Error creating or updating network interface {0} - {1}".format(self.name, str(exc)))
        new_nic = self.get_poller_result(poller)
        self.log("new_nic:")
        self.log(new_nic)
        self.log(new_nic.network_security_group)

        if len(new_nic.ip_configurations) > 0:
            for config in new_nic.ip_configurations:
                self.log("ip configurations")
                self.log(config)

        return nic_to_dict(new_nic)

    def delete_nic(self):
        try:
            poller = self.network_client.network_interfaces.delete(self.resource_group, self.name)
        except Exception, exc:
            self.fail("Error deleting network interface {0} - {1}".format(self.name, str(exc)))
        self.get_poller_result(poller)
        # Delete doesn't return anything. If we get this far, assume success
        self.results['results'] = 'Deleted'
        return True

    def get_public_ip_address(self, name):
        try:
            public_ip = self.network_client.public_ip_addresses.get(self.resource_group, name)
            return public_ip
        except CloudError:
            self.fail("Parameter error: public ip address {0} not found in resource group {1}".format(
                self.public_ip_address_name, self.resource_group))

    def get_subnet(self):
        try:
            subnet = self.network_client.subnets.get(self.resource_group,
                                                     self.virtual_network_name,
                                                     self.subnet_name)
            return subnet
        except CloudError:
            self.fail("Parameter error: subnet {0} not found in virtual network {1}".format(self.subnet_name,
                                                                                            self.virtual_network_name))

    def get_security_group(self, name):
        try:
            nsg = self.network_client.network_security_groups.get(self.resource_group, name)
            return nsg
        except CloudError:
            self.fail("Parameter error: network security group {0} not found.".format(
                self.security_group_name))

def main():
    if '--interactive' in sys.argv:
        # import the module here so we can reset the default complex args value
        import ansible.module_utils.basic

        ansible.module_utils.basic.MODULE_COMPLEX_ARGS = json.dumps(dict(
            resource_group = "rm_demo",
            name = "test-nic",
            state = "present",
            location = "West US",
            subnet_id = "subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/rm_demo/providers/Microsoft.Network/virtualNetworks/test-vnet/subnets/test-subnet-1",
            public_ip_id = None,
            log_mode = "stderr"
        ))

    AzureRMNetworkInterface().exec_module()

main()

