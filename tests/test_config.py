import textwrap

import config


def test_service_id_is_stable_and_slugified():
    host = {"ip": "192.168.50.13"}
    svc = {"name": "RSS Media Review"}
    assert config.service_id(host, svc) == "192_168_50_13_rss_media_review"


def test_service_id_falls_back_to_host_name_when_no_ip():
    assert config.service_id({"name": "Box"}, {"name": "S"}) == "box_s"


def test_iter_services_yields_every_service_with_id(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(textwrap.dedent("""
        hosts:
          - name: A
            ip: 10.0.0.1
            services:
              - name: One
                url: http://x/
              - name: Two
                systemd_unit: two.service
          - name: B
            ip: 10.0.0.2
            services:
              - name: Three
                docker_container: three
    """))
    cfg = config.load_config(cfg_file)
    ids = [sid for sid, _host, _svc in config.iter_services(cfg)]
    assert ids == ["10_0_0_1_one", "10_0_0_1_two", "10_0_0_2_three"]


def test_iter_services_empty_config():
    assert list(config.iter_services({})) == []
