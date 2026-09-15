;$M Meta untilchar 000204
;$M Frame X40.00 Y40.00
;$M Pos X0.00 Y0.00
;$M NumOps 1
;$M Op 0
;$M Type Vector
;$M Speed 1000
;$M Power 50.0
;$M Rep 1
;$M Time 1
;$M Thumb start X1 Y1
;$MT FF
;$M Thumb end

M5 ; Turn laser off
G21 ; Units in mm

; --- Job #ff0000 ---
F1000
G0 X0 Y40
M3 S128
G1 X40 Y40
G1 X40 Y0
G1 X0 Y0
G1 X0 Y40
M5
G0 X0 Y0

M5 ; Turn laser off
