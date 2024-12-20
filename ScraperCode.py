from enum import Enum

class ScraperCode(Enum):
    ARISTA = "A"
    RUCKUS = "R"
    CISCO = "C"
    HPE = "H"
    
    @classmethod
    def get(cls, value):
        for member in cls:
            if member.value == value:
                return member
