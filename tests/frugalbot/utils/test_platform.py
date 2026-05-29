from unittest.mock import patch

from frugalbot.utils.platform import get_platform_info


class TestGetPlatformInfoWindows:
    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_windows_x86_64_returns_windows_x64(
        self,
        mock_system,
        mock_machine,
        mock_release,
    ) -> None:
        # Given
        mock_system.return_value = "Windows"
        mock_machine.return_value = "x86_64"
        mock_release.return_value = "10"

        # When
        result = get_platform_info()

        # Then
        assert result == "Windows 10 x64"

    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_windows_amd64_returns_windows_x64(
        self,
        mock_system,
        mock_machine,
        mock_release,
    ) -> None:
        # Given
        mock_system.return_value = "Windows"
        mock_machine.return_value = "AMD64"
        mock_release.return_value = "11"

        # When
        result = get_platform_info()

        # Then
        assert result == "Windows 11 x64"

    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_windows_x86_returns_windows_x86(
        self,
        mock_system,
        mock_machine,
        mock_release,
    ) -> None:
        # Given
        mock_system.return_value = "Windows"
        mock_machine.return_value = "x86"
        mock_release.return_value = "10"

        # When
        result = get_platform_info()

        # Then
        assert result == "Windows 10 x86"

    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_windows_aarch64_returns_windows_x64(
        self,
        mock_system,
        mock_machine,
        mock_release,
    ) -> None:
        # Given
        mock_system.return_value = "Windows"
        mock_machine.return_value = "aarch64"
        mock_release.return_value = "11"

        # When
        result = get_platform_info()

        # Then
        assert result == "Windows 11 x64"


class TestGetPlatformInfoLinux:
    @patch("frugalbot.utils.platform.platform.freedesktop_os_release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_linux_freedesktop_available_returns_pretty_name(
        self,
        mock_system,
        mock_machine,
        mock_freedesktop,
    ) -> None:
        # Given
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        mock_freedesktop.return_value = {"PRETTY_NAME": "Ubuntu 24.04 LTS"}

        # When
        result = get_platform_info()

        # Then
        assert result == "Ubuntu 24.04 LTS x64"

    @patch("frugalbot.utils.platform.platform.freedesktop_os_release")
    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_linux_freedesktop_raises_attribute_error_returns_fallback(
        self,
        mock_system,
        mock_machine,
        mock_release,
        mock_freedesktop,
    ) -> None:
        # Given
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        mock_release.return_value = "6.1.0"
        mock_freedesktop.side_effect = AttributeError("Not available")

        # When
        result = get_platform_info()

        # Then
        assert result == "Linux 6.1.0 x64"

    @patch("frugalbot.utils.platform.platform.freedesktop_os_release")
    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_linux_freedesktop_raises_os_error_returns_fallback(
        self,
        mock_system,
        mock_machine,
        mock_release,
        mock_freedesktop,
    ) -> None:
        # Given
        mock_system.return_value = "Linux"
        mock_machine.return_value = "armv7l"
        mock_release.return_value = "5.15.0"
        mock_freedesktop.side_effect = OSError("Cannot read os-release")

        # When
        result = get_platform_info()

        # Then
        assert result == "Linux 5.15.0 x86"

    @patch("frugalbot.utils.platform.platform.freedesktop_os_release")
    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_linux_no_pretty_name_returns_linux_fallback(
        self,
        mock_system,
        mock_machine,
        mock_release,
        mock_freedesktop,
    ) -> None:
        # Given
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        mock_release.return_value = "6.5.0"
        mock_freedesktop.return_value = {"NAME": "Debian", "VERSION_ID": "12"}

        # When
        result = get_platform_info()

        # Then
        assert result == "Linux x64"


class TestGetPlatformInfoDarwin:
    @patch("frugalbot.utils.platform.platform.mac_ver")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_darwin_returns_macos_version(
        self,
        mock_system,
        mock_machine,
        mock_mac_ver,
    ) -> None:
        # Given
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"
        mock_mac_ver.return_value = ("15.3", "", "")

        # When
        result = get_platform_info()

        # Then
        assert result == "macOS 15.3 x64"

    @patch("frugalbot.utils.platform.platform.mac_ver")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_darwin_x86_64_returns_macos_x64(
        self,
        mock_system,
        mock_machine,
        mock_mac_ver,
    ) -> None:
        # Given
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "x86_64"
        mock_mac_ver.return_value = ("14.2", "", "")

        # When
        result = get_platform_info()

        # Then
        assert result == "macOS 14.2 x64"


class TestGetPlatformInfoUnknown:
    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_unknown_system_returns_generic_string(
        self,
        mock_system,
        mock_machine,
        mock_release,
    ) -> None:
        # Given
        mock_system.return_value = "FreeBSD"
        mock_machine.return_value = "amd64"
        mock_release.return_value = "14.0-RELEASE"

        # When
        result = get_platform_info()

        # Then
        assert result == "FreeBSD 14.0-RELEASE x64"

    @patch("frugalbot.utils.platform.platform.release")
    @patch("frugalbot.utils.platform.platform.machine")
    @patch("frugalbot.utils.platform.platform.system")
    def test_get_platform_info_with_unknown_system_and_x86_machine_returns_generic_x86(
        self,
        mock_system,
        mock_machine,
        mock_release,
    ) -> None:
        # Given
        mock_system.return_value = "OpenBSD"
        mock_machine.return_value = "i386"
        mock_release.return_value = "7.4"

        # When
        result = get_platform_info()

        # Then
        assert result == "OpenBSD 7.4 x86"
