package simfront.repository

import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository
import simfront.entity.NatureLien

@Repository
interface NatureLienRepository : JpaRepository<NatureLien, Long>
