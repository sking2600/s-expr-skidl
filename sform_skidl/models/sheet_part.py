from .part import Part
from .pin import Pin

class SheetPart(Part):
    """
    Virtual Part representing a Hierarchical Sheet in a schematic.
    """
    def __init__(self, name: str, filename: str, width=20.32, height=20.32):
        # Initialize as a generic part
        super().__init__(lib="Hierarchical", name=name)
        self.value = filename # Use value field to store filename
        self.dest = "schematic"
        self.is_sheet = True
        self.width = width
        self.height = height
        self.ref = "S" # S for Sheet? User can change.
        
    def add_port(self, net_name: str, direction: str = "input"):
        # Add a pin representing the port
        num = str(len(self._get_unique_pins()) + 1)
        pin = Pin(number=num, name=net_name)
        pin._part = self
        self._pins[num] = pin
        self._pins[net_name] = pin 
        # Default pos
        pin.position = (0, 0)

    def _get_unique_pins(self):
        # Helper to avoid duplicates from name/number aliasing in _pins
        seen = set()
        unique = []
        for p in self._pins.values():
            if id(p) not in seen:
                unique.append(p)
                seen.add(id(p))
        return unique

    def layout_ports(self):
        """Distribute ports on the sheet symbol edges."""
        # Simple heuristic: All ports on Left/Right
        pins = self._get_unique_pins()
        
        # Split by direction or arbitrary?
        # For now, put all on Left (Input-like) and Right (Output-like).
        # We don't track direction yet.
        # Just split 50/50.
        count = len(pins)
        left_count = (count + 1) // 2
        
        spacing = 2.54
        
        # Calculate required height
        req_height = max(left_count, count - left_count) * spacing + spacing
        if req_height > self.height:
            self.height = req_height
            
        # Left side
        y = -(self.height / 2) + spacing if self.height else 0
        # Wait, schematic coords.
        # Y is generally centered around 0 for symbol.
        # Top is +Y (Symbol Space).
        # Start from top?
        
        # Let's use Symbol Space (+Y up).
        # Top = Height/2. Bottom = -Height/2.
        
        current_y = (self.height / 2) - spacing
        
        for i, pin in enumerate(pins):
            if i < left_count:
                # Left Edge
                pin.position = (-self.width/2, current_y)
                current_y -= spacing
                if i == left_count - 1:
                    # Reset Y for Right side
                     current_y = (self.height / 2) - spacing
            else:
                # Right Edge
                pin.position = (self.width/2, current_y)
                current_y -= spacing
