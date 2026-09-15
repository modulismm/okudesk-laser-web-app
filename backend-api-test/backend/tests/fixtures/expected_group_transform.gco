;$M Meta untilchar 000204
;$M Frame X20.00 Y20.00
;$M Pos X0.00 Y0.00
;$M NumOps 1
;$M Op 0
;$M Type Vector
;$M Speed 1000
;$M Power 60.0
;$M Rep 1
;$M Time 1
;$M Thumb start X1 Y1
;$MT FF
;$M Thumb end

M5 ; Turn laser off
G21 ; Units in mm

; --- Job #0000ff ---
F1000
G0 X0 Y20
M3 S153
G1 X20 Y20
G1 X20 Y0
G1 X0 Y0
M5
G0 X0 Y0

M5 ; Turn laser off
