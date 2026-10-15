export const BUILDINGS = [
  {id: 'house-1', label: 'House 1', type: 'Residence', icon: '⌂', state: 'Residential unit', x: 42, z: 61, w: 21, d: 15, h: 8.5, wall: '#e7d4bd', roof: '#b98d73', description: 'North-west residence with a landscaped perimeter and driveway access from the inner loop.', facts: [['Level', 'Ground'], ['Access', 'Inner loop'], ['Model', '3D']]},
  {id: 'house-2', label: 'House 2', type: 'Residence', icon: '⌂', state: 'Residential unit', x: 42, z: 78, w: 21, d: 15, h: 8.5, wall: '#e7d4bd', roof: '#b98d73', description: 'South-west residence facing the central green and the western neighborhood loop.', facts: [['Level', 'Ground'], ['Access', 'West loop'], ['Model', '3D']]},
  {id: 'house-3', label: 'House 3', type: 'Residence', icon: '⌂', state: 'Residential unit', x: 119, z: 61, w: 21, d: 15, h: 8.5, wall: '#e7d4bd', roof: '#b98d73', description: 'North-east residence bordered by mature landscaping and the eastern access road.', facts: [['Level', 'Ground'], ['Access', 'Inner loop'], ['Model', '3D']]},
  {id: 'house-4', label: 'House 4', type: 'Residence', icon: '⌂', state: 'Residential unit', x: 119, z: 78, w: 21, d: 15, h: 8.5, wall: '#e7d4bd', roof: '#b98d73', description: 'South-east residence with a private garden edge and direct loop-road frontage.', facts: [['Level', 'Ground'], ['Access', 'East loop'], ['Model', '3D']]},
  {id: 'clubhouse', label: 'Clubhouse', type: 'Community', icon: '◆', state: 'Shared facility', x: 122, z: 24, w: 23, d: 19, h: 11, wall: '#ead7c8', roof: '#ad806b', description: 'The community clubhouse anchors the north-east amenity precinct beside the pool.', facts: [['Use', 'Community'], ['Zone', 'North'], ['Model', '3D']]},
  {id: 'guardhouse', label: 'Guardhouse', type: 'Security', icon: '◇', state: 'Entry control', x: 80, z: 101, w: 13, d: 10, h: 7, wall: '#d8c7b6', roof: '#8d7065', description: 'Primary vehicle-entry checkpoint positioned on the southern approach road.', facts: [['Use', 'Security'], ['Access', 'Main gate'], ['Model', '3D']]},
];

export const AMENITIES = [
  {id: 'pool', label: 'Swimming pool', type: 'Amenity', icon: '≈', state: 'Shared amenity', x: 80, z: 24, w: 32, d: 15, h: .7, description: 'Central outdoor swimming pool with a raised timber deck and shaded seating.', facts: [['Type', 'Outdoor'], ['Zone', 'North'], ['Depth', 'Illustrative']]},
  {id: 'garden', label: 'Garden', type: 'Amenity', icon: '✦', state: 'Landscaped space', x: 31, z: 24, r: 13, description: 'Circular community garden with a walking ring, benches, shade trees, and planted edges.', facts: [['Type', 'Garden'], ['Zone', 'North-west'], ['Access', 'Loop path']]},
];

export const TREE_POSITIONS = [
  [10, 10, 1], [23, 10, .82], [39, 9, .95], [55, 10, .75], [72, 9, .9], [91, 10, .76], [108, 9, .95], [139, 10, 1], [151, 18, .8],
  [10, 29, .85], [151, 35, .92], [9, 52, .78], [151, 58, .95], [9, 74, .92], [151, 79, .82], [9, 96, .9], [151, 99, .98],
  [20, 98, .72], [34, 99, .84], [51, 98, .78], [64, 96, .7], [98, 97, .82], [113, 98, .72], [133, 98, .9],
  [22, 35, .7], [45, 34, .62], [105, 35, .7], [137, 35, .72], [24, 56, .66], [61, 57, .76], [99, 57, .72], [137, 57, .72],
  [25, 82, .72], [62, 80, .86], [98, 80, .78], [137, 81, .78], [69, 62, .7], [91, 63, .72], [69, 75, .76], [92, 75, .82],
];

export const FLOWERS = [
  [16, 20, '#f2c84b'], [20, 31, '#ef7199'], [48, 18, '#f0799e'], [56, 34, '#f5d44c'], [103, 17, '#f0cb42'], [142, 25, '#e96d99'],
  [20, 63, '#f3cd43'], [58, 50, '#e86e9c'], [103, 49, '#f2cc43'], [140, 69, '#e86d99'], [18, 88, '#ef729c'], [104, 89, '#efcb44'],
];
