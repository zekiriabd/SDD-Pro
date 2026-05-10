package simfront.mapper

import simfront.dto.output.ReferentielItemOutputDto
import simfront.entity.Format
import simfront.entity.MotifInactivite
import simfront.entity.NatureLien

fun Format.toOutputDto() = ReferentielItemOutputDto(id = this.id, libelle = this.libelle)
fun NatureLien.toOutputDto() = ReferentielItemOutputDto(id = this.id, libelle = this.libelle)
fun MotifInactivite.toOutputDto() = ReferentielItemOutputDto(id = this.id, libelle = this.libelle)
