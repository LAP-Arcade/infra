locals {
  # order matters here, ip_reservation is based on list index
  vpn_users = [
    "jarvis", # 192.168.27.65
    "tina", # 192.168.27.66... etc
    "tina-mobile",
    "adamaq01",
    "adamaq02",
    "human",
    "tina-homepc",
  ]
}

terraform {
  required_providers {
    freebox = {
      source = "registry.terraform.io/NikolaLohinski/freebox"
    }
  }

  backend "s3" {
    bucket = "terraform"
    key    = "lap/freebox.tfstate"
    region = "laffey-ii"

    endpoints = {
      s3 = "https://s3.tina.moe"
    }

    use_path_style              = true
    use_lockfile                = true
    skip_credentials_validation = true
    skip_region_validation      = true
  }
}

variable "FREEBOX_TOKEN" {
  sensitive = true
  default   = "http://mafreebox.freebox.fr"
}

variable "FREEBOX_ENDPOINT" {
  sensitive = true
}

provider "freebox" {
  endpoint    = var.FREEBOX_ENDPOINT
  api_version = "v16"
  app_id      = "terraform-provider-freebox"
  token       = var.FREEBOX_TOKEN
}

resource "freebox_vpn_server" "wireguard" {
  vpn_id      = "wireguard"
  enabled     = true
  enable_ipv4 = true
  port        = 9078
}

import {
  to = freebox_vpn_server.wireguard
  id = "wireguard"
}

resource "freebox_vpn_user" "vpn_users" {
  for_each = { for index, login in local.vpn_users : login => index }

  login = each.key
  type  = "wireguard"
  ip_reservation = "192.168.27.${65 + each.value}"
}
