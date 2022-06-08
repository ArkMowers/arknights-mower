from typing import Dict, List, Tuple, Union

import numpy as np
from numpy.typing import NDArray

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
Hash = List[int]
Score = Tuple[float, float, float, float]

# Operation Plan
OpePlan = Tuple[str, int]

# BaseConstruct Plan
BasePlan = Dict[str, List[str]]

# Parameter
ParamArgs = List[str]
