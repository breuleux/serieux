from dataclasses import dataclass

from ovld import Medley
from ovld.dependent import Regexp

from serieux import Context, Serieux, deserialize, serialize


@dataclass
class RGB:
    red: int
    green: int
    blue: int


@Serieux.extend
class RGBSerializer(Medley):
    """Custom serializer for RGB colors to/from hex strings."""

    def serialize(self, t: type[RGB], obj: RGB, ctx: Context):
        """Convert RGB to hex string format #rrggbb."""
        return f"#{obj.red:02x}{obj.green:02x}{obj.blue:02x}"

    def deserialize(self, t: type[RGB], obj: Regexp[r"^#[0-9a-fA-F]{6}$"], ctx: Context):
        """Convert hex string #rrggbb to RGB."""
        hex_str = obj.lstrip("#")
        red = int(hex_str[0:2], 16)
        green = int(hex_str[2:4], 16)
        blue = int(hex_str[4:6], 16)
        return RGB(red=red, green=green, blue=blue)


def main():
    # Test serialization
    color = RGB(red=255, green=128, blue=0)
    serialized = serialize(RGB, color)
    assert serialized == "#ff8000"
    print(f"Serialized color: {serialized}")  # Should print: #ff8000

    # Test deserialization
    deserialized = deserialize(RGB, "#ff8000")
    assert deserialized == color
    print(f"Deserialized color: {deserialized}")  # Should print: RGB(red=255, green=128, blue=0)

    # Test with a list of colors
    colors = [RGB(255, 0, 0), RGB(0, 255, 0), RGB(0, 0, 255)]
    serialized_list = serialize(list[RGB], colors)
    assert serialized_list == ["#ff0000", "#00ff00", "#0000ff"]
    print(f"Serialized list: {serialized_list}")  # Should print: ["#ff0000", "#00ff00", "#0000ff"]

    # Test deserialization of a list
    deserialized_list = deserialize(list[RGB], ["#ff0000", "#00ff00", "#0000ff"])
    assert deserialized_list == colors, f"Expected {colors}, got {deserialized_list}"
    print(
        f"Deserialized list: {deserialized_list}"
    )  # Should print: [RGB(255,0,0), RGB(0,255,0), RGB(0,0,255)]


if __name__ == "__main__":
    main()
