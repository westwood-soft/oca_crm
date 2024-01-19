from odoo.upgrade import util


def migrate(cr, version):
    cr.execute(
        """
            SELECT res_id
              FROM ir_model_data d
             WHERE NOT EXISTS (SELECT 1
                                 FROM ir_model_data
                                WHERE id != d.id
                                  AND res_id = d.res_id
                                  AND model = d.model
                                  AND module != d.module)
               AND module = 'crm_claim'
               AND model = 'ir.ui.view'
          ORDER BY id DESC
            """
    )
    for view_id in cr.fetchall():
        util.remove_view(cr, view_id=view_id)

    cr.execute(
        """
            SELECT res_id
              FROM ir_model_data d
             WHERE NOT EXISTS (SELECT 1
                                 FROM ir_model_data
                                WHERE id != d.id
                                  AND res_id = d.res_id
                                  AND model = d.model
                                  AND module != d.module)
               AND module = 'crm_claim'
               AND model = 'ir.ui.menu'
          ORDER BY id DESC
    """
    )
    menu_ids = cr.fetchall()
    util.remove_menus(cr, menu_ids)

    # crm_claim to helpdesk_ticket
    util.create_column(cr, "helpdesk_stage", "_stage_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_stage
                (_stage_id, name, sequence, legend_blocked, legend_normal, legend_done)
                SELECT id, name, sequence, '{ "de_DE": "Blockiert", "en_EN": "Blocked" }', '{ "de_DE": "In Bearbeitung", "en_EN": "In Progress" }', '{ "de_DE": "Erledigt", "en_EN": "Done" }'
               FROM crm_claim_stage
               WHERE NOT name ->> 'en_US' in ('New', 'Erledigt')
               """
    )

    cr.execute(
        """
        UPDATE helpdesk_stage SET
        (_stage_id) = (SELECT id FROM crm_claim_stage WHERE name ->> 'en_US' = 'New')
        WHERE name ->> 'en_US' = 'New'
        """
    )

    cr.execute(
        """
        UPDATE helpdesk_stage SET
        (_stage_id) = (SELECT id FROM crm_claim_stage WHERE name ->> 'en_US' = 'Erledigt')
        WHERE name ->> 'en_US' = 'Solved'
        """
    )

    util.create_column(cr, "helpdesk_ticket_type", "_categ_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_ticket_type
                (_categ_id, name)
               SELECT id, name
               FROM crm_claim_category
        """
    )

    util.create_column(cr, "helpdesk_ticket", "_claim_id", "int4")
    util.create_column(cr, "helpdesk_ticket", "_categ_id", "int4")
    util.create_column(cr, "helpdesk_ticket", "_stage_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_ticket
               (_claim_id, _categ_id, _stage_id, ticket_ref, name, active, sale_order_id, create_date, write_date, close_date, description, partner_id, user_id, company_id, kanban_state)
               SELECT
               id, categ_id, stage_id, nextval('helpdesk_ticket_id_seq'), name, active, CAST(split_part(model_ref_id, ',', 2) AS INTEGER) as sale_order_id, create_date, write_date, date_closed, description, partner_id, user_id, company_id, 'normal'
               FROM crm_claim WHERE model_ref_id like 'sale.order,%' and exists(select 1 from sale_order where id = cast(split_part(model_ref_id, ',', 2) as integer))
        """
    )

    util.merge_model(cr, "crm.claim.stage", "helpdesk.stage")
    util.merge_model(cr, "crm.claim.category", "helpdesk.ticket.type")

    cr.execute(
        """
           UPDATE helpdesk_ticket SET
            ticket_type_id = htt.id
           FROM helpdesk_ticket_type htt
           WHERE htt._categ_id = helpdesk_ticket._categ_id
        """
    )

    cr.execute(
        """
           UPDATE helpdesk_ticket SET
            stage_id = hs.id
           FROM helpdesk_stage hs
           WHERE hs._stage_id = helpdesk_ticket._stage_id
        """
    )

    cr.execute(
        "SELECT id FROM res_company WHERE NOT EXISTS (SELECT 1 FROM helpdesk_team ht WHERE ht.company_id = res_company.id)"
    )

    cr.execute(
        """INSERT INTO helpdesk_team
               (name,
                active, company_id, sequence, color,
                assign_method, use_alias, allow_portal_ticket_closing, use_website_helpdesk_form, use_website_helpdesk_livechat,
                use_website_helpdesk_forum, use_website_helpdesk_slides, use_helpdesk_timesheet, use_helpdesk_sale_timesheet, use_credit_notes,
                use_coupons, use_product_returns, use_product_repairs, use_twitter, use_rating,
                portal_show_rating, use_sla, auto_close_ticket, auto_close_day, to_stage_id,
                use_fsm, privacy_visibility, auto_assignment, ticket_properties, use_website_helpdesk_knowledge)
           SELECT
               '{"de_DE": "Support ' || res_company.name || '", "en_US": "Support ' || res_company.name || '"}' as name,
               true as active, res_company.id as company_id, 10 as sequence, 0 as color,
               'randomly' as assign_method, true as use_alias, false as allow_portal_ticket_closing, false as use_website_helpdesk_form, false as use_website_helpdesk_livechat,
               false as use_website_helpdesk_forum, false as use_website_helpdesk_slides, false as use_helpdesk_timesheet, false as use_helpdesk_sale_timesheet, false as use_credit_notes,
               false as use_coupons, false as use_product_returns, false as use_product_repairs, false as use_twitter, false as use_rating,
               false as portal_show_rating, false as use_sla, false as auto_close_ticket, 7 as auto_close_day, 3 as to_stage_id,
               false as use_fsm, 'internal' privacy_visibility, false as auto_assignment, false as ticket_properties, false as use_website_helpdesk_knowledge
           FROM res_company WHERE NOT EXISTS (SELECT 1 FROM helpdesk_team ht WHERE ht.company_id = res_company.id)
           """
    )

    cr.execute(
        """
           UPDATE mail_message SET
               model = 'helpdesk.ticket',
               res_id = ht.id
           FROM helpdesk_ticket ht
           WHERE mail_message.model = 'crm.claim'
           AND mail_message.res_id = ht._claim_id
           AND ht._claim_id IS NOT NULL
        """
    )

    cr.execute(
        """
           UPDATE ir_attachment SET
               res_model = 'helpdesk.ticket',
               res_id = ht.id
           FROM helpdesk_ticket ht
           WHERE ir_attachment.model = 'crm.claim'
           AND ir_attachment.res_id = ht._claim_id
           AND ht._claim_id IS NOT NULL
        """
    )

    cr.execute(
        """
            SELECT id, _claim_id FROM helpdesk_ticket WHERE _claim_id IS NOT NULL
        """
    )
    ticket_claim_tuples = cr.fetchall()
    mapping = {ticket_id: claim_id for ticket_id, claim_id in ticket_claim_tuples}
    util.replace_record_references_batch(cr, mapping, "helpdesk.ticket", "crm.claim")

    cr.execute(
        """
            UPDATE helpdesk_ticket AS ht SET company_id = rp.company_id FROM res_partner AS rp WHERE rp.id = ht.partner_id
        """
    )

    cr.execute(
        """
            UPDATE helpdesk_ticket AS ht SET team_id = team.id FROM helpdesk_team AS team WHERE ht.company_id = team.company_id
        """
    )

    util.merge_model(cr, "crm.claim", "helpdesk.ticket")
    util.remove_column(cr, "helpdesk_stage", "_stage_id")
    util.remove_column(cr, "helpdesk_ticket_type", "_categ_id")
    util.remove_column(cr, "helpdesk_ticket", "_stage_id")
    util.remove_column(cr, "helpdesk_ticket", "_categ_id")
    util.remove_column(cr, "helpdesk_ticket", "_claim_id")
