import numpy as np
from numpy.typing import NDArray
from typing import Tuple, Literal, List, Union


# Operation Plan
Plan = Tuple[str, int]

# Image
Image = NDArray[np.int8]
Pixel = Tuple[int, int, int]

GrayImage = NDArray[np.int8]
GrayPixel = int

# Recognizer
Range = Tuple[int, int]
Coordinate = Tuple[int, int]
Scope = Tuple[Coordinate, Coordinate]
Slice = Tuple[Range, Range]
Rectangle = Tuple[Coordinate, Coordinate, Coordinate, Coordinate]
Location = Union[Rectangle, Scope, Coordinate]

# Matcher
Hash = List[Literal[0, 1]]
Score = Tuple[float, float, float, float]
